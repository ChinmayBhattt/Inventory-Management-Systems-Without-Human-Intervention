package services

import (
	"database/sql"
	"fmt"
	"math"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/models"
)

type ReplenishmentService struct {
	db *database.DB
}

func NewReplenishmentService(db *database.DB) *ReplenishmentService {
	return &ReplenishmentService{db: db}
}

// CalculateSafetyStock computes: SS = z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2)
func CalculateSafetyStock(avgDailyDemand, stdDailyDemand float64, leadTimeDays int, leadTimeStd, serviceLevelZ float64) int {
	L := float64(leadTimeDays)
	variance := (L * math.Pow(stdDailyDemand, 2)) + (math.Pow(avgDailyDemand, 2) * math.Pow(leadTimeStd, 2))
	if variance < 0 {
		variance = 0
	}
	ss := serviceLevelZ * math.Sqrt(variance)
	return int(math.Ceil(ss))
}

// CalculateReorderPoint computes: ROP = d * L + SS
func CalculateReorderPoint(avgDailyDemand float64, leadTimeDays int, safetyStock int) int {
	leadDemand := avgDailyDemand * float64(leadTimeDays)
	return int(math.Ceil(leadDemand)) + safetyStock
}

// CalculateEOQ computes: EOQ = sqrt( (2 * D * S) / H )
func CalculateEOQ(annualDemand float64, fixedOrderCost, unitCost, holdingCostPct float64) int {
	H := unitCost * holdingCostPct
	if H <= 0 {
		H = 1.0
	}
	eoq := math.Sqrt((2.0 * annualDemand * fixedOrderCost) / H)
	return int(math.Max(1.0, math.Ceil(eoq)))
}

func (s *ReplenishmentService) GetPolicies(warehouseID string) ([]models.ReorderPolicy, error) {
	query := `
		SELECT 
			rp.id, rp.product_id, rp.warehouse_id, rp.service_level_z, rp.lead_time_days,
			rp.holding_cost_annual_pct, rp.fixed_order_cost, rp.safety_stock, rp.reorder_point,
			rp.economic_order_quantity, rp.auto_approve_max_po_value, rp.is_autonomous,
			p.id, p.sku, p.name, p.category, p.unit_cost, p.unit_price
		FROM reorder_policies rp
		LEFT JOIN products p ON rp.product_id = p.id
	`
	var rows *sql.Rows
	var err error
	if warehouseID != "" {
		query += ` WHERE rp.warehouse_id = ? ORDER BY p.sku ASC`
		rows, err = s.db.Query(query, warehouseID)
	} else {
		query += ` ORDER BY p.sku ASC`
		rows, err = s.db.Query(query)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query policies: %w", err)
	}
	defer rows.Close()

	var policies []models.ReorderPolicy
	for rows.Next() {
		var rp models.ReorderPolicy
		var p models.Product
		err := rows.Scan(
			&rp.ID, &rp.ProductID, &rp.WarehouseID, &rp.ServiceLevelZ, &rp.LeadTimeDays,
			&rp.HoldingCostAnnualPct, &rp.FixedOrderCost, &rp.SafetyStock, &rp.ReorderPoint,
			&rp.EconomicOrderQuantity, &rp.AutoApproveMaxPOValue, &rp.IsAutonomous,
			&p.ID, &p.SKU, &p.Name, &p.Category, &p.UnitCost, &p.UnitPrice,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan policy: %w", err)
		}
		rp.Product = &p
		policies = append(policies, rp)
	}
	return policies, nil
}

func (s *ReplenishmentService) UpdatePolicy(policyID string, req *models.ReorderPolicyUpdateRequest) (*models.ReorderPolicy, error) {
	nowStr := time.Now().UTC().Format(time.RFC3339)

	var query string
	var args []interface{}

	if req.SafetyStock != nil {
		query = "UPDATE reorder_policies SET safety_stock = ?, updated_at = ? WHERE id = ?"
		args = []interface{}{*req.SafetyStock, nowStr, policyID}
	} else if req.ReorderPoint != nil {
		query = "UPDATE reorder_policies SET reorder_point = ?, updated_at = ? WHERE id = ?"
		args = []interface{}{*req.ReorderPoint, nowStr, policyID}
	} else if req.EconomicOrderQuantity != nil {
		query = "UPDATE reorder_policies SET economic_order_quantity = ?, updated_at = ? WHERE id = ?"
		args = []interface{}{*req.EconomicOrderQuantity, nowStr, policyID}
	} else if req.AutoApproveMaxPOValue != nil {
		query = "UPDATE reorder_policies SET auto_approve_max_po_value = ?, updated_at = ? WHERE id = ?"
		args = []interface{}{*req.AutoApproveMaxPOValue, nowStr, policyID}
	} else if req.IsAutonomous != nil {
		query = "UPDATE reorder_policies SET is_autonomous = ?, updated_at = ? WHERE id = ?"
		args = []interface{}{*req.IsAutonomous, nowStr, policyID}
	} else {
		query = "UPDATE reorder_policies SET updated_at = ? WHERE id = ?"
		args = []interface{}{nowStr, policyID}
	}

	_, err := s.db.Exec(query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to update policy: %w", err)
	}

	policies, err := s.GetPolicies("")
	if err != nil {
		return nil, err
	}
	for _, p := range policies {
		if p.ID == policyID {
			return &p, nil
		}
	}
	return nil, fmt.Errorf("policy not found after update: %s", policyID)
}

func (s *ReplenishmentService) EvaluateSweep() (*models.ReplenishmentRunResult, error) {
	type Candidate struct {
		ProductID             string
		WarehouseID           string
		SKU                   string
		Name                  string
		Available             int
		OnOrder               int
		ReorderPoint          int
		EOQ                   int
		AutoApproveMax        float64
		UnitCost              float64
		DefaultSupplierID     string
		LeadTimeDays          int
	}

	query := `
		SELECT 
			p.id, s.warehouse_id, p.sku, p.name, s.available, s.on_order,
			rp.reorder_point, rp.economic_order_quantity, rp.auto_approve_max_po_value,
			p.unit_cost, p.default_supplier_id, rp.lead_time_days
		FROM stock_levels s
		JOIN products p ON s.product_id = p.id
		JOIN reorder_policies rp ON (rp.product_id = p.id AND rp.warehouse_id = s.warehouse_id)
		WHERE rp.is_autonomous = 1
	`
	rows, err := s.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("sweep query failed: %w", err)
	}
	defer rows.Close()

	var candidates []Candidate
	for rows.Next() {
		var c Candidate
		var defSupp sql.NullString
		err := rows.Scan(
			&c.ProductID, &c.WarehouseID, &c.SKU, &c.Name, &c.Available, &c.OnOrder,
			&c.ReorderPoint, &c.EOQ, &c.AutoApproveMax,
			&c.UnitCost, &defSupp, &c.LeadTimeDays,
		)
		if err != nil {
			return nil, err
		}
		c.DefaultSupplierID = defSupp.String
		candidates = append(candidates, c)
	}

	tx, err := s.db.Begin()
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()

	evaluatedCount := len(candidates)
	poCreatedCount := 0
	totalCommitted := 0.0
	now := time.Now().UTC()
	nowStr := now.Format(time.RFC3339)

	for _, c := range candidates {
		effectiveInventory := c.Available + c.OnOrder
		if effectiveInventory <= c.ReorderPoint {
			orderQty := c.EOQ
			if orderQty <= 0 {
				orderQty = int(math.Max(50.0, float64(c.ReorderPoint-effectiveInventory+30)))
			}
			poCost := float64(orderQty) * c.UnitCost
			approvalMode := "AUTONOMOUS"
			poStatus := "AUTO_APPROVED"

			if c.AutoApproveMax > 0 && poCost > c.AutoApproveMax {
				approvalMode = "MANUAL_REVIEW"
				poStatus = "PENDING_APPROVAL"
			}

			poID := fmt.Sprintf("po-%d-%s", now.UnixNano(), c.SKU[:4])
			poNum := fmt.Sprintf("PO-%s-%04d", now.Format("20060102"), poCreatedCount+1)
			expectedETA := now.Add(time.Duration(c.LeadTimeDays) * 24 * time.Hour).Format(time.RFC3339)
			pdfPath := fmt.Sprintf("./storage/purchase_orders/%s.pdf", poNum)

			suppID := c.DefaultSupplierID
			if suppID == "" {
				suppID = "supp-001"
			}

			// Insert Purchase Order
			_, err = tx.Exec(`
				INSERT INTO purchase_orders (
					id, po_number, supplier_id, warehouse_id, status, approval_mode, total_cost,
					expected_delivery_date, pdf_storage_path, notes, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			`, poID, poNum, suppID, c.WarehouseID, poStatus, approvalMode, poCost, expectedETA, pdfPath, "Algorithmic sweep auto-generation", nowStr, nowStr)
			if err != nil {
				return nil, fmt.Errorf("failed to insert PO: %w", err)
			}

			// Insert PO Item
			poItemID := fmt.Sprintf("poi-%d", now.UnixNano())
			_, err = tx.Exec(`
				INSERT INTO po_items (id, po_id, product_id, quantity_ordered, quantity_received, unit_cost, created_at, updated_at)
				VALUES (?, ?, ?, ?, 0, ?, ?, ?)
			`, poItemID, poID, c.ProductID, orderQty, c.UnitCost, nowStr, nowStr)
			if err != nil {
				return nil, fmt.Errorf("failed to insert PO item: %w", err)
			}

			// Update stock_levels.on_order
			_, err = tx.Exec(`
				UPDATE stock_levels 
				SET on_order = on_order + ?, updated_at = ?
				WHERE product_id = ? AND warehouse_id = ?
			`, orderQty, nowStr, c.ProductID, c.WarehouseID)
			if err != nil {
				return nil, fmt.Errorf("failed to update on_order: %w", err)
			}

			// If manual review, insert Alert
			if poStatus == "PENDING_APPROVAL" {
				alertID := fmt.Sprintf("alt-%d", now.UnixNano())
				msg := fmt.Sprintf("Purchase Order %s ($%.2f) exceeds autonomous threshold ($%.2f). Manager review required.", poNum, poCost, c.AutoApproveMax)
				_, _ = tx.Exec(`
					INSERT INTO alerts (id, alert_type, severity, product_id, warehouse_id, message, context_data, status, created_at, updated_at)
					VALUES (?, 'MANUAL_PO_REVIEW', 'HIGH', ?, ?, ?, ?, 'OPEN', ?, ?)
				`, alertID, c.ProductID, c.WarehouseID, msg, fmt.Sprintf(`{"po_number":"%s","total_cost":%.2f}`, poNum, poCost), nowStr, nowStr)
			}

			poCreatedCount++
			totalCommitted += poCost
		}
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("failed to commit sweep: %w", err)
	}

	return &models.ReplenishmentRunResult{
		EvaluatedSKUs:         evaluatedCount,
		PurchaseOrdersCreated: poCreatedCount,
		TotalCommittedValue:   totalCommitted,
		Timestamp:             time.Now().UTC().Format(time.RFC3339),
	}, nil
}
