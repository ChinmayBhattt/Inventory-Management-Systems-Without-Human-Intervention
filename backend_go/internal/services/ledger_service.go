package services

import (
	"database/sql"
	"errors"
	"fmt"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/models"
)

type LedgerService struct {
	db *database.DB
}

func NewLedgerService(db *database.DB) *LedgerService {
	return &LedgerService{db: db}
}

func (s *LedgerService) GetStockLevels() ([]models.StockLevel, error) {
	query := `
		SELECT 
			s.id, s.product_id, s.warehouse_id, s.on_hand, s.reserved, s.available, s.on_order, s.created_at, s.updated_at,
			p.id, p.sku, p.name, p.category, p.unit_cost, p.unit_price
		FROM stock_levels s
		LEFT JOIN products p ON s.product_id = p.id
		ORDER BY p.sku ASC
	`
	rows, err := s.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to query stock levels: %w", err)
	}
	defer rows.Close()

	var results []models.StockLevel
	for rows.Next() {
		var sl models.StockLevel
		var p models.Product
		var createdAt, updatedAt string

		err := rows.Scan(
			&sl.ID, &sl.ProductID, &sl.WarehouseID, &sl.OnHand, &sl.Reserved, &sl.Available, &sl.OnOrder, &createdAt, &updatedAt,
			&p.ID, &p.SKU, &p.Name, &p.Category, &p.UnitCost, &p.UnitPrice,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan stock level row: %w", err)
		}
		sl.Product = &p
		results = append(results, sl)
	}
	return results, nil
}

func (s *LedgerService) GetTransactions(limit int, txType string) ([]models.InventoryTransaction, error) {
	if limit <= 0 || limit > 500 {
		limit = 100
	}

	baseQuery := `
		SELECT 
			t.id, t.product_id, t.warehouse_id, t.transaction_type, t.quantity_delta, 
			t.reference_type, t.reference_id, t.idempotency_key, t.created_at,
			p.id, p.sku, p.name, p.category
		FROM inventory_transactions t
		LEFT JOIN products p ON t.product_id = p.id
	`
	var rows *sql.Rows
	var err error

	if txType != "" && txType != "ALL" {
		query := baseQuery + ` WHERE t.transaction_type = ? ORDER BY t.created_at DESC LIMIT ?`
		rows, err = s.db.Query(query, txType, limit)
	} else {
		query := baseQuery + ` ORDER BY t.created_at DESC LIMIT ?`
		rows, err = s.db.Query(query, limit)
	}

	if err != nil {
		return nil, fmt.Errorf("failed to query transactions: %w", err)
	}
	defer rows.Close()

	var results []models.InventoryTransaction
	for rows.Next() {
		var it models.InventoryTransaction
		var p models.Product
		var createdAtStr string

		var refType, refID, idemKey sql.NullString
		err := rows.Scan(
			&it.ID, &it.ProductID, &it.WarehouseID, &it.TransactionType, &it.QuantityDelta,
			&refType, &refID, &idemKey, &createdAtStr,
			&p.ID, &p.SKU, &p.Name, &p.Category,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan transaction row: %w", err)
		}
		it.ReferenceType = refType.String
		it.ReferenceID = refID.String
		it.IdempotencyKey = idemKey.String
		it.Product = &p
		it.CreatedAt, _ = time.Parse(time.RFC3339, createdAtStr)
		results = append(results, it)
	}
	return results, nil
}

func (s *LedgerService) RecordTransaction(tx *sql.Tx, it *models.InventoryTransaction) error {
	// 1. Idempotency Check
	if it.IdempotencyKey != "" {
		var existsID string
		err := tx.QueryRow(`SELECT id FROM inventory_transactions WHERE idempotency_key = ?`, it.IdempotencyKey).Scan(&existsID)
		if err == nil && existsID != "" {
			// Already processed idempotently
			return nil
		}
	}

	if it.ID == "" {
		it.ID = fmt.Sprintf("tx-%d", time.Now().UnixNano())
	}
	nowStr := time.Now().UTC().Format(time.RFC3339)

	// 2. Insert Transaction Record
	insertTx := `
		INSERT INTO inventory_transactions (
			id, product_id, warehouse_id, transaction_type, quantity_delta, 
			reference_type, reference_id, idempotency_key, metadata_json, created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`
	_, err := tx.Exec(
		insertTx,
		it.ID, it.ProductID, it.WarehouseID, it.TransactionType, it.QuantityDelta,
		it.ReferenceType, it.ReferenceID, it.IdempotencyKey, it.MetadataJSON, nowStr, nowStr,
	)
	if err != nil {
		return fmt.Errorf("failed to insert transaction: %w", err)
	}

	// 3. Update stock_levels
	updateStock := `
		UPDATE stock_levels 
		SET on_hand = on_hand + ?, 
		    available = (on_hand + ?) - reserved,
		    updated_at = ?
		WHERE product_id = ? AND warehouse_id = ?
	`
	res, err := tx.Exec(updateStock, it.QuantityDelta, it.QuantityDelta, nowStr, it.ProductID, it.WarehouseID)
	if err != nil {
		return fmt.Errorf("failed to update stock level: %w", err)
	}
	rowsAffected, _ := res.RowsAffected()
	if rowsAffected == 0 {
		return errors.New("stock level record not found for product and warehouse")
	}

	return nil
}

