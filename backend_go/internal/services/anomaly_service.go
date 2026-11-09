package services

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/config"
	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/models"
)

type AnomalyService struct {
	db  *database.DB
	cfg *config.Config
}

func NewAnomalyService(db *database.DB, cfg *config.Config) *AnomalyService {
	return &AnomalyService{db: db, cfg: cfg}
}

func (s *AnomalyService) ListAlerts(statusFilter string) ([]models.Alert, error) {
	baseQuery := `
		SELECT 
			a.id, a.alert_type, a.severity, a.product_id, a.warehouse_id, a.message,
			a.context_data, a.status, a.resolved_at, a.created_at,
			p.id, p.sku, p.name, p.category
		FROM alerts a
		LEFT JOIN products p ON a.product_id = p.id
	`
	var rows *sql.Rows
	var err error

	if statusFilter != "" && statusFilter != "ALL" {
		query := baseQuery + ` WHERE a.status = ? ORDER BY a.created_at DESC`
		rows, err = s.db.Query(query, statusFilter)
	} else {
		query := baseQuery + ` ORDER BY a.created_at DESC`
		rows, err = s.db.Query(query)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query alerts: %w", err)
	}
	defer rows.Close()

	var alerts []models.Alert
	for rows.Next() {
		var a models.Alert
		var p models.Product
		var pid, wid, resAt sql.NullString
		var createdAtStr string
		var pID, pSKU, pName, pCat sql.NullString

		err := rows.Scan(
			&a.ID, &a.AlertType, &a.Severity, &pid, &wid, &a.Message,
			&a.ContextData, &a.Status, &resAt, &createdAtStr,
			&pID, &pSKU, &pName, &pCat,
		)
		if err != nil {
			return nil, err
		}

		if pid.Valid {
			a.ProductID = &pid.String
		}
		if wid.Valid {
			a.WarehouseID = &wid.String
		}
		if resAt.Valid {
			t, _ := time.Parse(time.RFC3339, resAt.String)
			a.ResolvedAt = &t
		}
		a.CreatedAt, _ = time.Parse(time.RFC3339, createdAtStr)

		if pID.Valid {
			p.ID = pID.String
			p.SKU = pSKU.String
			p.Name = pName.String
			p.Category = pCat.String
			a.Product = &p
		}

		alerts = append(alerts, a)
	}
	return alerts, nil
}

func (s *AnomalyService) ResolveAlert(alertID, resolutionNotes string) (*models.Alert, error) {
	nowStr := time.Now().UTC().Format(time.RFC3339)
	res, err := s.db.Exec(`
		UPDATE alerts 
		SET status = 'RESOLVED', resolved_at = ?, message = message || ' ' || ?
		WHERE id = ?
	`, nowStr, fmt.Sprintf("[Resolved: %s]", resolutionNotes), alertID)
	if err != nil {
		return nil, err
	}
	rowsAffected, _ := res.RowsAffected()
	if rowsAffected == 0 {
		return nil, errors.New("alert not found")
	}

	alerts, err := s.ListAlerts("")
	if err != nil {
		return nil, err
	}
	for _, a := range alerts {
		if a.ID == alertID {
			return &a, nil
		}
	}
	return nil, errors.New("alert not found after resolution")
}

func (s *AnomalyService) AuditStockDrift() (*models.AnomalyAuditResult, error) {
	query := `
		SELECT 
			s.product_id, s.warehouse_id, s.on_hand, s.reserved, p.sku,
			COALESCE((SELECT SUM(quantity_delta) FROM inventory_transactions WHERE product_id = s.product_id AND warehouse_id = s.warehouse_id), 0) AS ledger_sum
		FROM stock_levels s
		JOIN products p ON s.product_id = p.id
	`
	rows, err := s.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to run drift audit query: %w", err)
	}
	defer rows.Close()

	var anomalies []models.AnomalyAuditItem
	totalCount := 0
	driftCount := 0
	selfHealedCount := 0
	now := time.Now().UTC()
	nowStr := now.Format(time.RFC3339)

	for rows.Next() {
		var productID, warehouseID, sku string
		var cachedOnHand, reserved, ledgerSum int
		if err := rows.Scan(&productID, &warehouseID, &cachedOnHand, &reserved, &sku, &ledgerSum); err != nil {
			return nil, err
		}
		totalCount++
		discrepancy := cachedOnHand - ledgerSum
		isSync := (discrepancy == 0)
		action := "NONE_SYNCHRONIZED"

		if !isSync {
			driftCount++
			// Self-heal: correct cached on_hand to match mathematical ledger truth
			newOnHand := ledgerSum
			newAvail := newOnHand - reserved
			_, _ = s.db.Exec(`
				UPDATE stock_levels 
				SET on_hand = ?, available = ?, updated_at = ?
				WHERE product_id = ? AND warehouse_id = ?
			`, newOnHand, newAvail, nowStr, productID, warehouseID)

			selfHealedCount++
			action = fmt.Sprintf("SELF_HEALED: on_hand reset from %d to %d", cachedOnHand, newOnHand)

			// Log alert
			alertID := fmt.Sprintf("alt-drift-%d", now.UnixNano())
			msg := fmt.Sprintf("Stock drift detected for %s. Cached: %d, Ledger Truth: %d, Discrepancy: %d. Self-healing applied.", sku, cachedOnHand, ledgerSum, discrepancy)
			_, _ = s.db.Exec(`
				INSERT INTO alerts (id, alert_type, severity, product_id, warehouse_id, message, context_data, status, created_at, updated_at)
				VALUES (?, 'STOCK_DRIFT', 'CRITICAL', ?, ?, ?, ?, 'OPEN', ?, ?)
			`, alertID, productID, warehouseID, msg, fmt.Sprintf(`{"sku":"%s","discrepancy":%d}`, sku, discrepancy), nowStr, nowStr)

			// Notify Slack if configured
			s.dispatchSlackAlert("STOCK_DRIFT", "CRITICAL", msg)
		}

		anomalies = append(anomalies, models.AnomalyAuditItem{
			SKU:              sku,
			CachedOnHand:     cachedOnHand,
			LedgerSumOnHand:  ledgerSum,
			Discrepancy:      discrepancy,
			IsSynchronized:   isSync,
			SelfHealedAction: action,
		})
	}

	return &models.AnomalyAuditResult{
		TotalEvaluated: totalCount,
		DriftDetected:  driftCount,
		SelfHealed:     selfHealedCount,
		Anomalies:      anomalies,
	}, nil
}

func (s *AnomalyService) dispatchSlackAlert(alertType, severity, message string) {
	if s.cfg.SlackWebhookURL == "" {
		return
	}
	go func() {
		emoji := "🚨"
		if severity != "CRITICAL" {
			emoji = "⚠️"
		}
		payload := map[string]string{
			"text": fmt.Sprintf("%s *AutoStock Alert [%s]*: `%s`\n>%s", emoji, severity, alertType, message),
		}
		body, _ := json.Marshal(payload)
		client := &http.Client{Timeout: 3 * time.Second}
		_, _ = client.Post(s.cfg.SlackWebhookURL, "application/json", bytes.NewBuffer(body))
	}()
}
