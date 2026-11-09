package services

import (
	"database/sql"
	"errors"
	"fmt"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/models"
)

type POService struct {
	db *database.DB
}

func NewPOService(db *database.DB) *POService {
	return &POService{db: db}
}

func (s *POService) ListPurchaseOrders(statusFilter string) ([]models.PurchaseOrder, error) {
	baseQuery := `
		SELECT 
			po.id, po.po_number, po.supplier_id, po.warehouse_id, po.status, po.approval_mode,
			po.total_cost, po.expected_delivery_date, po.confirmed_delivery_date, po.pdf_storage_path,
			po.notes, po.created_at, po.updated_at,
			s.id, s.name, s.email, s.lead_time_days,
			w.id, w.code, w.name
		FROM purchase_orders po
		LEFT JOIN suppliers s ON po.supplier_id = s.id
		LEFT JOIN warehouses w ON po.warehouse_id = w.id
	`
	var rows *sql.Rows
	var err error

	if statusFilter != "" && statusFilter != "ALL" {
		query := baseQuery + ` WHERE po.status = ? ORDER BY po.created_at DESC`
		rows, err = s.db.Query(query, statusFilter)
	} else {
		query := baseQuery + ` ORDER BY po.created_at DESC`
		rows, err = s.db.Query(query)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query purchase orders: %w", err)
	}
	defer rows.Close()

	var orders []models.PurchaseOrder
	for rows.Next() {
		var po models.PurchaseOrder
		var supp models.Supplier
		var wh models.Warehouse
		var expDateStr, createdAtStr, updatedAtStr string
		var confDateStr, pdfPath, notes sql.NullString
		var suppID, suppName, suppEmail sql.NullString
		var suppLead sql.NullInt64
		var whID, whCode, whName sql.NullString

		err := rows.Scan(
			&po.ID, &po.PONumber, &po.SupplierID, &po.WarehouseID, &po.Status, &po.ApprovalMode,
			&po.TotalCost, &expDateStr, &confDateStr, &pdfPath,
			&notes, &createdAtStr, &updatedAtStr,
			&suppID, &suppName, &suppEmail, &suppLead,
			&whID, &whCode, &whName,
		)
		if err != nil {
			return nil, err
		}

		po.PDFStoragePath = pdfPath.String
		po.Notes = notes.String
		po.ExpectedDeliveryDate, _ = time.Parse(time.RFC3339, expDateStr)
		po.CreatedAt, _ = time.Parse(time.RFC3339, createdAtStr)
		po.UpdatedAt, _ = time.Parse(time.RFC3339, updatedAtStr)
		if confDateStr.Valid {
			t, _ := time.Parse(time.RFC3339, confDateStr.String)
			po.ConfirmedDeliveryDate = &t
		}

		if suppID.Valid {
			supp.ID = suppID.String
			supp.Name = suppName.String
			supp.Email = suppEmail.String
			supp.LeadTimeDays = int(suppLead.Int64)
			po.Supplier = &supp
		}

		if whID.Valid {
			wh.ID = whID.String
			wh.Code = whCode.String
			wh.Name = whName.String
			po.Warehouse = &wh
		}

		// Fetch items for this PO
		itemRows, err := s.db.Query(`
			SELECT poi.id, poi.po_id, poi.product_id, poi.quantity_ordered, poi.quantity_received, poi.unit_cost,
			       p.id, p.sku, p.name, p.category
			FROM po_items poi
			LEFT JOIN products p ON poi.product_id = p.id
			WHERE poi.po_id = ?
		`, po.ID)
		if err == nil {
			for itemRows.Next() {
				var it models.POItem
				var p models.Product
				_ = itemRows.Scan(&it.ID, &it.POID, &it.ProductID, &it.QuantityOrdered, &it.QuantityReceived, &it.UnitCost,
					&p.ID, &p.SKU, &p.Name, &p.Category)
				it.Product = &p
				po.Items = append(po.Items, it)
			}
			itemRows.Close()
		}

		orders = append(orders, po)
	}
	return orders, nil
}

func (s *POService) ApprovePurchaseOrder(poID, reason string) (*models.PurchaseOrder, error) {
	nowStr := time.Now().UTC().Format(time.RFC3339)

	var poNumber string
	var status string
	err := s.db.QueryRow(`SELECT po_number, status FROM purchase_orders WHERE id = ?`, poID).Scan(&poNumber, &status)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, errors.New("purchase order not found")
		}
		return nil, err
	}

	noteExtra := fmt.Sprintf("[Manager Approved: %s]", reason)
	updatePO := `
		UPDATE purchase_orders 
		SET status = 'SENT', approval_mode = 'MANUAL_APPROVED', notes = notes || ' ' || ?, updated_at = ?
		WHERE id = ?
	`
	_, err = s.db.Exec(updatePO, noteExtra, nowStr, poID)
	if err != nil {
		return nil, fmt.Errorf("failed to update PO: %w", err)
	}

	// Resolve any associated alerts
	_, _ = s.db.Exec(`
		UPDATE alerts 
		SET status = 'RESOLVED', resolved_at = ? 
		WHERE alert_type = 'MANUAL_PO_REVIEW' AND context_data LIKE ?
	`, nowStr, "%"+poNumber+"%")

	orders, err := s.ListPurchaseOrders("")
	if err != nil {
		return nil, err
	}
	for _, po := range orders {
		if po.ID == poID {
			return &po, nil
		}
	}
	return nil, errors.New("failed to retrieve updated PO")
}
