package services

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"sync"
	"time"

	"autonomous-inventory-backend-go/backend_go/internal/config"
	"autonomous-inventory-backend-go/backend_go/internal/database"
	"autonomous-inventory-backend-go/backend_go/internal/models"
)

type OrderService struct {
	db     *database.DB
	cfg    *config.Config
	locks  map[string]*sync.Mutex
	lockMu sync.Mutex
}

func NewOrderService(db *database.DB, cfg *config.Config) *OrderService {
	return &OrderService{
		db:    db,
		cfg:   cfg,
		locks: make(map[string]*sync.Mutex),
	}
}

func (s *OrderService) getLock(key string) *sync.Mutex {
	s.lockMu.Lock()
	defer s.lockMu.Unlock()
	if l, exists := s.locks[key]; exists {
		return l
	}
	l := &sync.Mutex{}
	s.locks[key] = l
	return l
}

func (s *OrderService) VerifyShopifySignature(rawBody []byte, hmacHeader string) bool {
	if hmacHeader == "" || s.cfg.ShopifyWebhookSecret == "" {
		return false
	}
	mac := hmac.New(sha256.New, []byte(s.cfg.ShopifyWebhookSecret))
	mac.Write(rawBody)
	computedHash := mac.Sum(nil)
	computedHMAC := base64.StdEncoding.EncodeToString(computedHash)

	return subtle.ConstantTimeCompare([]byte(computedHMAC), []byte(hmacHeader)) == 1
}

func (s *OrderService) CreateOrder(req *models.OrderCreateRequest, channel string) (*models.Order, error) {
	if len(req.Items) == 0 {
		return nil, errors.New("order must contain at least one item")
	}

	// Lock all products in order to prevent race conditions
	for _, item := range req.Items {
		l := s.getLock(fmt.Sprintf("%s:%s", item.ProductID, req.WarehouseID))
		l.Lock()
		defer l.Unlock()
	}

	tx, err := s.db.Begin()
	if err != nil {
		return nil, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	// 1. Idempotency check
	if req.IdempotencyKey != "" {
		var existingID, orderNum string
		var totalAmount float64
		err := tx.QueryRow(`SELECT id, order_number, total_amount FROM orders WHERE idempotency_key = ?`, req.IdempotencyKey).Scan(&existingID, &orderNum, &totalAmount)
		if err == nil {
			return &models.Order{
				ID:             existingID,
				OrderNumber:    orderNum,
				Channel:        channel,
				Status:         "CONFIRMED",
				IdempotencyKey: req.IdempotencyKey,
				WarehouseID:    req.WarehouseID,
				TotalAmount:    totalAmount,
			}, nil
		}
	}

	// 2. Validate stock availability and calculate total
	var totalCost float64
	for _, item := range req.Items {
		var available int
		err := tx.QueryRow(`SELECT available FROM stock_levels WHERE product_id = ? AND warehouse_id = ?`, item.ProductID, req.WarehouseID).Scan(&available)
		if err != nil {
			return nil, fmt.Errorf("product %s not found in warehouse %s", item.ProductID, req.WarehouseID)
		}
		if available < item.Quantity {
			return nil, fmt.Errorf("insufficient available stock for product %s (available: %d, requested: %d)", item.ProductID, available, item.Quantity)
		}
		totalCost += float64(item.Quantity) * item.UnitPrice
	}

	// 3. Create Order
	orderID := fmt.Sprintf("ord-%d", time.Now().UnixNano())
	orderNum := fmt.Sprintf("ORD-%s", time.Now().Format("20060102150405"))
	nowStr := time.Now().UTC().Format(time.RFC3339)

	insertOrder := `
		INSERT INTO orders (id, order_number, channel, status, idempotency_key, warehouse_id, total_amount, created_at, updated_at)
		VALUES (?, ?, ?, 'CONFIRMED', ?, ?, ?, ?, ?)
	`
	_, err = tx.Exec(insertOrder, orderID, orderNum, channel, req.IdempotencyKey, req.WarehouseID, totalCost, nowStr, nowStr)
	if err != nil {
		return nil, fmt.Errorf("failed to insert order: %w", err)
	}

	// 4. Create Order Items & Reserve Stock
	var orderItems []models.OrderItem
	for _, item := range req.Items {
		itemID := fmt.Sprintf("oi-%d-%s", time.Now().UnixNano(), item.ProductID[:4])
		_, err = tx.Exec(`
			INSERT INTO order_items (id, order_id, product_id, quantity, unit_price, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?, ?, ?)
		`, itemID, orderID, item.ProductID, item.Quantity, item.UnitPrice, nowStr, nowStr)
		if err != nil {
			return nil, fmt.Errorf("failed to insert order item: %w", err)
		}

		// Reserve stock: increment reserved, decrement available
		_, err = tx.Exec(`
			UPDATE stock_levels 
			SET reserved = reserved + ?, 
			    available = on_hand - (reserved + ?),
			    updated_at = ?
			WHERE product_id = ? AND warehouse_id = ?
		`, item.Quantity, item.Quantity, nowStr, item.ProductID, req.WarehouseID)
		if err != nil {
			return nil, fmt.Errorf("failed to reserve stock: %w", err)
		}

		orderItems = append(orderItems, models.OrderItem{
			ID:        itemID,
			OrderID:   orderID,
			ProductID: item.ProductID,
			Quantity:  item.Quantity,
			UnitPrice: item.UnitPrice,
		})
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("failed to commit order: %w", err)
	}

	return &models.Order{
		ID:             orderID,
		OrderNumber:    orderNum,
		Channel:        channel,
		Status:         "CONFIRMED",
		IdempotencyKey: req.IdempotencyKey,
		WarehouseID:    req.WarehouseID,
		TotalAmount:    totalCost,
		Items:          orderItems,
		CreatedAt:      time.Now(),
		UpdatedAt:      time.Now(),
	}, nil
}
