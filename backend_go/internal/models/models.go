package models

import "time"

type User struct {
	ID             string    `json:"id"`
	Email          string    `json:"email"`
	HashedPassword string    `json:"-"`
	FullName       string    `json:"full_name"`
	Role           string    `json:"role"`
	IsActive       bool      `json:"is_active"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

type Warehouse struct {
	ID        string    `json:"id"`
	Code      string    `json:"code"`
	Name      string    `json:"name"`
	Address   string    `json:"address"`
	IsActive  bool      `json:"is_active"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Supplier struct {
	ID                string    `json:"id"`
	Name              string    `json:"name"`
	Email             string    `json:"email"`
	APIEndpoint       string    `json:"api_endpoint"`
	LeadTimeDays      int       `json:"lead_time_days"`
	MinimumOrderValue float64   `json:"minimum_order_value"`
	ReliabilityScore  float64   `json:"reliability_score"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type Product struct {
	ID                string    `json:"id"`
	SKU               string    `json:"sku"`
	Name              string    `json:"name"`
	Description       string    `json:"description"`
	Category          string    `json:"category"`
	UnitCost          float64   `json:"unit_cost"`
	UnitPrice         float64   `json:"unit_price"`
	DefaultSupplierID string    `json:"default_supplier_id"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type StockLevel struct {
	ID               string    `json:"id"`
	ProductID        string    `json:"product_id"`
	WarehouseID      string    `json:"warehouse_id"`
	OnHand           int       `json:"on_hand"`
	Reserved         int       `json:"reserved"`
	Available        int       `json:"available"`
	OnOrder          int       `json:"on_order"`
	LastReconciledAt time.Time `json:"last_reconciled_at"`
	Product          *Product  `json:"product,omitempty"`
	Warehouse        *Warehouse `json:"warehouse,omitempty"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

type ReorderPolicy struct {
	ID                    string   `json:"id"`
	ProductID             string   `json:"product_id"`
	WarehouseID           string   `json:"warehouse_id"`
	ServiceLevelZ         float64  `json:"service_level_z"`
	LeadTimeDays          int      `json:"lead_time_days"`
	HoldingCostAnnualPct  float64  `json:"holding_cost_annual_pct"`
	FixedOrderCost        float64  `json:"fixed_order_cost"`
	SafetyStock           int      `json:"safety_stock"`
	ReorderPoint          int      `json:"reorder_point"`
	EconomicOrderQuantity int      `json:"economic_order_quantity"`
	AutoApproveMaxPOValue float64  `json:"auto_approve_max_po_value"`
	IsAutonomous          bool     `json:"is_autonomous"`
	Product               *Product `json:"product,omitempty"`
	CreatedAt             time.Time `json:"created_at"`
	UpdatedAt             time.Time `json:"updated_at"`
}

type InventoryTransaction struct {
	ID              string    `json:"id"`
	ProductID       string    `json:"product_id"`
	WarehouseID     string    `json:"warehouse_id"`
	TransactionType string    `json:"transaction_type"` // SALE, RECEIPT, RETURN, DAMAGE, ADJUSTMENT
	QuantityDelta   int       `json:"quantity_delta"`
	ReferenceType   string    `json:"reference_type"`
	ReferenceID     string    `json:"reference_id"`
	IdempotencyKey  string    `json:"idempotency_key"`
	MetadataJSON    string    `json:"metadata_json"`
	Product         *Product  `json:"product,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
}

type Order struct {
	ID             string      `json:"id"`
	OrderNumber    string      `json:"order_number"`
	Channel        string      `json:"channel"`
	Status         string      `json:"status"`
	IdempotencyKey string      `json:"idempotency_key"`
	WarehouseID    string      `json:"warehouse_id"`
	TotalAmount    float64     `json:"total_amount"`
	Items          []OrderItem `json:"items,omitempty"`
	CreatedAt      time.Time   `json:"created_at"`
	UpdatedAt      time.Time   `json:"updated_at"`
}

type OrderItem struct {
	ID        string   `json:"id"`
	OrderID   string   `json:"order_id"`
	ProductID string   `json:"product_id"`
	Quantity  int      `json:"quantity"`
	UnitPrice float64  `json:"unit_price"`
	Product   *Product `json:"product,omitempty"`
}

type PurchaseOrder struct {
	ID                    string     `json:"id"`
	PONumber              string     `json:"po_number"`
	SupplierID            string     `json:"supplier_id"`
	WarehouseID           string     `json:"warehouse_id"`
	Status                string     `json:"status"` // PENDING_APPROVAL, AUTO_APPROVED, APPROVED, SENT, CONFIRMED, RECEIVED, CANCELLED
	ApprovalMode          string     `json:"approval_mode"`
	TotalCost             float64    `json:"total_cost"`
	ExpectedDeliveryDate  time.Time  `json:"expected_delivery_date"`
	ConfirmedDeliveryDate *time.Time `json:"confirmed_delivery_date,omitempty"`
	PDFStoragePath        string     `json:"pdf_storage_path"`
	Notes                 string     `json:"notes"`
	Items                 []POItem   `json:"items,omitempty"`
	Supplier              *Supplier  `json:"supplier,omitempty"`
	Warehouse             *Warehouse `json:"warehouse,omitempty"`
	CreatedAt             time.Time  `json:"created_at"`
	UpdatedAt             time.Time  `json:"updated_at"`
}

type POItem struct {
	ID               string   `json:"id"`
	POID             string   `json:"po_id"`
	ProductID        string   `json:"product_id"`
	QuantityOrdered  int      `json:"quantity_ordered"`
	QuantityReceived int      `json:"quantity_received"`
	UnitCost         float64  `json:"unit_cost"`
	Product          *Product `json:"product,omitempty"`
}

type Forecast struct {
	ID                     string    `json:"id"`
	ProductID              string    `json:"product_id"`
	WarehouseID            string    `json:"warehouse_id"`
	ForecastDate           time.Time `json:"forecast_date"`
	HorizonDays            int       `json:"horizon_days"`
	PredictedDemand        float64   `json:"predicted_demand"`
	ConfidenceIntervalLower float64  `json:"confidence_interval_lower"`
	ConfidenceIntervalUpper float64  `json:"confidence_interval_upper"`
	ModelName              string    `json:"model_name"`
	ModelVersion           string    `json:"model_version"`
	BacktestWAPE           float64   `json:"backtest_wape"`
	BacktestMAPE           float64   `json:"backtest_mape"`
}

type Alert struct {
	ID          string    `json:"id"`
	AlertType   string    `json:"alert_type"` // STOCK_DRIFT, OVERDUE_PO, CRITICAL_LOW_STOCK, MANUAL_PO_REVIEW
	Severity    string    `json:"severity"`   // LOW, MEDIUM, HIGH, CRITICAL
	ProductID   *string   `json:"product_id"`
	WarehouseID *string   `json:"warehouse_id"`
	Message     string    `json:"message"`
	ContextData string    `json:"context_data"`
	Status      string    `json:"status"` // OPEN, RESOLVED, DISMISSED
	ResolvedAt  *time.Time `json:"resolved_at,omitempty"`
	Product     *Product  `json:"product,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
}

// DTOs
type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type LoginResponse struct {
	AccessToken string `json:"access_token"`
	TokenType   string `json:"token_type"`
	User        User   `json:"user"`
}

type OrderCreateRequest struct {
	WarehouseID    string             `json:"warehouse_id"`
	CustomerID     string             `json:"customer_id"`
	IdempotencyKey string             `json:"idempotency_key"`
	Items          []OrderItemRequest `json:"items"`
}

type OrderItemRequest struct {
	ProductID string  `json:"product_id"`
	Quantity  int     `json:"quantity"`
	UnitPrice float64 `json:"unit_price"`
}

type POApproveRequest struct {
	ApprovalReason string `json:"approval_reason"`
}

type AlertResolveRequest struct {
	ResolutionNotes string `json:"resolution_notes"`
}

type ReorderPolicyUpdateRequest struct {
	SafetyStock           *int     `json:"safety_stock,omitempty"`
	ReorderPoint          *int     `json:"reorder_point,omitempty"`
	EconomicOrderQuantity *int     `json:"economic_order_quantity,omitempty"`
	ServiceLevelZ         *float64 `json:"service_level_z,omitempty"`
	AutoApproveMaxPOValue *float64 `json:"auto_approve_max_po_value,omitempty"`
	IsAutonomous          *bool    `json:"is_autonomous,omitempty"`
}

type GoodsReceiptRequest struct {
	PONumber string                  `json:"po_number"`
	Items    []GoodsReceiptItemRequest `json:"items"`
}

type GoodsReceiptItemRequest struct {
	ProductID        string `json:"product_id"`
	QuantityReceived int    `json:"quantity_received"`
}

type ForecastEvaluationResponse struct {
	SKU            string  `json:"sku"`
	ModelName      string  `json:"model_name"`
	WAPE           float64 `json:"wape"`
	MAPE           float64 `json:"mape"`
	Status         string  `json:"status"`
	Recommendation string  `json:"recommendation"`
}

type ForecastTimelinePoint struct {
	Date            string  `json:"date"`
	ActualDemand    *int    `json:"actual_demand"`
	PredictedDemand float64 `json:"predicted_demand"`
	ConfidenceLower float64 `json:"confidence_lower"`
	ConfidenceUpper float64 `json:"confidence_upper"`
}

type AnomalyAuditResult struct {
	TotalEvaluated int                `json:"total_evaluated"`
	DriftDetected  int                `json:"drift_detected"`
	SelfHealed     int                `json:"self_healed"`
	Anomalies      []AnomalyAuditItem `json:"anomalies"`
}

type AnomalyAuditItem struct {
	SKU              string `json:"sku"`
	CachedOnHand     int    `json:"cached_on_hand"`
	LedgerSumOnHand  int    `json:"ledger_sum_on_hand"`
	Discrepancy      int    `json:"discrepancy"`
	IsSynchronized   bool   `json:"is_synchronized"`
	SelfHealedAction string `json:"self_healed_action"`
}

type ReplenishmentRunResult struct {
	EvaluatedSKUs          int     `json:"evaluated_skus"`
	PurchaseOrdersCreated  int     `json:"purchase_orders_created"`
	TotalCommittedValue    float64 `json:"total_committed_value"`
	Timestamp              string  `json:"timestamp"`
}

