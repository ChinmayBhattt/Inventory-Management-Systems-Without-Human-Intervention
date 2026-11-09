package services

import (
	"database/sql"
	"errors"
	"fmt"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/models"
)

type GoodsReceiptService struct {
	db            *database.DB
	ledgerService *LedgerService
}

func NewGoodsReceiptService(db *database.DB, ledgerService *LedgerService) *GoodsReceiptService {
	return &GoodsReceiptService{db: db, ledgerService: ledgerService}
}

func (s *GoodsReceiptService) ReceiveGoods(req *models.GoodsReceiptRequest) error {
	if len(req.Items) == 0 {
		return errors.New("must receive at least one item")
	}

	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	// 1. Find PO
	var poID, warehouseID, status string
	err = tx.QueryRow(`SELECT id, warehouse_id, status FROM purchase_orders WHERE po_number = ?`, req.PONumber).Scan(&poID, &warehouseID, &status)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return fmt.Errorf("purchase order not found: %s", req.PONumber)
		}
		return err
	}

	now := time.Now().UTC()
	nowStr := now.Format(time.RFC3339)

	// 2. Process each received item
	for _, it := range req.Items {
		if it.QuantityReceived <= 0 {
			continue
		}

		// Update po_items
		res, err := tx.Exec(`
			UPDATE po_items 
			SET quantity_received = quantity_received + ?, updated_at = ?
			WHERE po_id = ? AND product_id = ?
		`, it.QuantityReceived, nowStr, poID, it.ProductID)
		if err != nil {
			return fmt.Errorf("failed to update PO item: %w", err)
		}
		rowsAff, _ := res.RowsAffected()
		if rowsAff == 0 {
			return fmt.Errorf("item %s not found in PO %s", it.ProductID, req.PONumber)
		}

		// Update stock_levels: on_hand += qty, on_order -= qty
		_, err = tx.Exec(`
			UPDATE stock_levels 
			SET on_hand = on_hand + ?,
			    on_order = MAX(0, on_order - ?),
			    available = (on_hand + ?) - reserved,
			    updated_at = ?
			WHERE product_id = ? AND warehouse_id = ?
		`, it.QuantityReceived, it.QuantityReceived, it.QuantityReceived, nowStr, it.ProductID, warehouseID)
		if err != nil {
			return fmt.Errorf("failed to update stock levels: %w", err)
		}

		// Record RECEIPT transaction in ledger
		txID := fmt.Sprintf("tx-grn-%d-%s", now.UnixNano(), it.ProductID[:4])
		idemKey := fmt.Sprintf("grn-%s-%s-%d", req.PONumber, it.ProductID, now.Unix())
		_, err = tx.Exec(`
			INSERT INTO inventory_transactions (
				id, product_id, warehouse_id, transaction_type, quantity_delta,
				reference_type, reference_id, idempotency_key, metadata_json, created_at, updated_at
			) VALUES (?, ?, ?, 'RECEIPT', ?, 'PURCHASE_ORDER', ?, ?, ?, ?, ?)
		`, txID, it.ProductID, warehouseID, it.QuantityReceived, req.PONumber, idemKey, `{"source":"GRN"}`, nowStr, nowStr)
		if err != nil {
			return fmt.Errorf("failed to insert RECEIPT transaction: %w", err)
		}
	}

	// 3. Check if all items received
	var totalOrdered, totalReceived int
	err = tx.QueryRow(`SELECT SUM(quantity_ordered), SUM(quantity_received) FROM po_items WHERE po_id = ?`, poID).Scan(&totalOrdered, &totalReceived)
	if err == nil {
		newStatus := "RECEIVED"
		if totalReceived < totalOrdered {
			newStatus = "PARTIALLY_RECEIVED"
		}
		_, _ = tx.Exec(`UPDATE purchase_orders SET status = ?, updated_at = ? WHERE id = ?`, newStatus, nowStr, poID)
	}

	return tx.Commit()
}
