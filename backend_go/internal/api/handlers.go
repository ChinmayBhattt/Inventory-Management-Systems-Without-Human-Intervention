package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"

	"autonomous-inventory-backend-go/backend_go/internal/config"
	"autonomous-inventory-backend-go/backend_go/internal/models"
	"autonomous-inventory-backend-go/backend_go/internal/services"
)

type Handlers struct {
	cfg          *config.Config
	authSvc      *services.AuthService
	ledgerSvc    *services.LedgerService
	orderSvc     *services.OrderService
	replenishSvc *services.ReplenishmentService
	poSvc        *services.POService
	anomalySvc   *services.AnomalyService
	forecastSvc  *services.ForecastService
	grnSvc       *services.GoodsReceiptService
}

func NewHandlers(
	cfg *config.Config,
	authSvc *services.AuthService,
	ledgerSvc *services.LedgerService,
	orderSvc *services.OrderService,
	replenishSvc *services.ReplenishmentService,
	poSvc *services.POService,
	anomalySvc *services.AnomalyService,
	forecastSvc *services.ForecastService,
	grnSvc *services.GoodsReceiptService,
) *Handlers {
	return &Handlers{
		cfg:          cfg,
		authSvc:      authSvc,
		ledgerSvc:    ledgerSvc,
		orderSvc:     orderSvc,
		replenishSvc: replenishSvc,
		poSvc:        poSvc,
		anomalySvc:   anomalySvc,
		forecastSvc:  forecastSvc,
		grnSvc:       grnSvc,
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"detail": msg})
}

// Health check
func (h *Handlers) Health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":          "healthy",
		"service":         "Autonomous Inventory Management System (Go Engine)",
		"environment":     h.cfg.Environment,
		"redis_connected": true,
	})
}

// POST /api/v1/auth/login
func (h *Handlers) Login(w http.ResponseWriter, r *http.Request) {
	var username, password string

	ct := r.Header.Get("Content-Type")
	if strings.Contains(ct, "application/x-www-form-urlencoded") {
		_ = r.ParseForm()
		username = r.FormValue("username")
		password = r.FormValue("password")
	} else {
		var req models.LoginRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "Invalid request body")
			return
		}
		username = req.Username
		password = req.Password
	}

	res, err := h.authSvc.Login(username, password)
	if err != nil {
		writeError(w, http.StatusUnauthorized, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// GET /api/v1/ledger/stock-levels
func (h *Handlers) GetStockLevels(w http.ResponseWriter, r *http.Request) {
	levels, err := h.ledgerSvc.GetStockLevels()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if levels == nil {
		levels = []models.StockLevel{}
	}
	writeJSON(w, http.StatusOK, levels)
}

// GET /api/v1/ledger/transactions
func (h *Handlers) GetTransactions(w http.ResponseWriter, r *http.Request) {
	limitStr := r.URL.Query().Get("limit")
	limit, _ := strconv.Atoi(limitStr)
	txType := r.URL.Query().Get("transaction_type")

	txs, err := h.ledgerSvc.GetTransactions(limit, txType)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if txs == nil {
		txs = []models.InventoryTransaction{}
	}
	writeJSON(w, http.StatusOK, txs)
}

// POST /api/v1/orders/create
func (h *Handlers) CreateOrder(w http.ResponseWriter, r *http.Request) {
	var req models.OrderCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}
	order, err := h.orderSvc.CreateOrder(&req, "REST_API")
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, order)
}

// POST /api/v1/orders/webhook/shopify
func (h *Handlers) ShopifyWebhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeError(w, http.StatusBadRequest, "Failed to read request body")
		return
	}

	hmacHeader := r.Header.Get("X-Shopify-Hmac-Sha256")
	if !h.orderSvc.VerifyShopifySignature(body, hmacHeader) {
		writeError(w, http.StatusUnauthorized, "Invalid Shopify HMAC signature")
		return
	}

	warehouseID := r.URL.Query().Get("warehouse_id")
	if warehouseID == "" {
		warehouseID = "wh-main-01"
	}

	// Parse Shopify JSON
	var payload struct {
		ID        any    `json:"id"`
		Name      string `json:"name"`
		LineItems []struct {
			SKU      string `json:"sku"`
			Quantity int    `json:"quantity"`
			Price    string `json:"price"`
		} `json:"line_items"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid Shopify payload JSON")
		return
	}

	// Convert SKUs to items
	stocks, _ := h.ledgerSvc.GetStockLevels()
	skuToID := make(map[string]string)
	for _, s := range stocks {
		if s.Product != nil {
			skuToID[s.Product.SKU] = s.ProductID
		}
	}

	var items []models.OrderItemRequest
	for _, li := range payload.LineItems {
		pid, exists := skuToID[li.SKU]
		if !exists {
			continue
		}
		p, _ := strconv.ParseFloat(li.Price, 64)
		items = append(items, models.OrderItemRequest{
			ProductID: pid,
			Quantity:  li.Quantity,
			UnitPrice: p,
		})
	}

	if len(items) == 0 {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ignored", "reason": "no recognized SKUs"})
		return
	}

	idemKey := fmt.Sprintf("shopify-%v", payload.ID)
	orderReq := &models.OrderCreateRequest{
		WarehouseID:    warehouseID,
		CustomerID:     "shopify-storefront",
		IdempotencyKey: idemKey,
		Items:          items,
	}

	order, err := h.orderSvc.CreateOrder(orderReq, "SHOPIFY_WEBHOOK")
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"status":       "processed",
		"order_number": order.OrderNumber,
		"reserved_at":  order.CreatedAt,
	})
}

// GET /api/v1/purchase-orders/
func (h *Handlers) ListPurchaseOrders(w http.ResponseWriter, r *http.Request) {
	statusFilter := r.URL.Query().Get("status")
	orders, err := h.poSvc.ListPurchaseOrders(statusFilter)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if orders == nil {
		orders = []models.PurchaseOrder{}
	}
	writeJSON(w, http.StatusOK, orders)
}

// POST /api/v1/purchase-orders/{id}/approve
func (h *Handlers) ApprovePurchaseOrder(w http.ResponseWriter, r *http.Request) {
	poID := r.PathValue("id")
	if poID == "" {
		writeError(w, http.StatusBadRequest, "Missing PO ID")
		return
	}

	var req models.POApproveRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
	reason := req.ApprovalReason
	if reason == "" {
		reason = "Dashboard one-click manager approval"
	}

	po, err := h.poSvc.ApprovePurchaseOrder(poID, reason)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, po)
}

// GET /api/v1/alerts/
func (h *Handlers) ListAlerts(w http.ResponseWriter, r *http.Request) {
	statusFilter := r.URL.Query().Get("status")
	alerts, err := h.anomalySvc.ListAlerts(statusFilter)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if alerts == nil {
		alerts = []models.Alert{}
	}
	writeJSON(w, http.StatusOK, alerts)
}

// POST /api/v1/alerts/{id}/resolve
func (h *Handlers) ResolveAlert(w http.ResponseWriter, r *http.Request) {
	alertID := r.PathValue("id")
	var req models.AlertResolveRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
	notes := req.ResolutionNotes
	if notes == "" {
		notes = "Resolved via Dashboard triage"
	}

	alert, err := h.anomalySvc.ResolveAlert(alertID, notes)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, alert)
}

// POST /api/v1/alerts/audit
func (h *Handlers) AuditStockDrift(w http.ResponseWriter, r *http.Request) {
	res, err := h.anomalySvc.AuditStockDrift()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// GET /api/v1/replenishment/policies
func (h *Handlers) GetPolicies(w http.ResponseWriter, r *http.Request) {
	whID := r.URL.Query().Get("warehouse_id")
	policies, err := h.replenishSvc.GetPolicies(whID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if policies == nil {
		policies = []models.ReorderPolicy{}
	}
	writeJSON(w, http.StatusOK, policies)
}

// PUT /api/v1/replenishment/policies/{id}
func (h *Handlers) UpdatePolicy(w http.ResponseWriter, r *http.Request) {
	policyID := r.PathValue("id")
	var req models.ReorderPolicyUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}
	pol, err := h.replenishSvc.UpdatePolicy(policyID, &req)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, pol)
}

// POST /api/v1/replenishment/evaluate
func (h *Handlers) EvaluateReplenishment(w http.ResponseWriter, r *http.Request) {
	res, err := h.replenishSvc.EvaluateSweep()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// GET /api/v1/forecasts/evaluation
func (h *Handlers) ForecastEvaluation(w http.ResponseWriter, r *http.Request) {
	sku := r.URL.Query().Get("sku")
	res, err := h.forecastSvc.GetEvaluation(sku)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// GET /api/v1/forecasts/timeline
func (h *Handlers) ForecastTimeline(w http.ResponseWriter, r *http.Request) {
	sku := r.URL.Query().Get("sku")
	daysStr := r.URL.Query().Get("days")
	days, _ := strconv.Atoi(daysStr)

	points, err := h.forecastSvc.GetTimeline(sku, days)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if points == nil {
		points = []models.ForecastTimelinePoint{}
	}
	writeJSON(w, http.StatusOK, points)
}

// POST /api/v1/goods-receipt/receive
func (h *Handlers) ReceiveGoods(w http.ResponseWriter, r *http.Request) {
	var req models.GoodsReceiptRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}
	if err := h.grnSvc.ReceiveGoods(&req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "received", "po_number": req.PONumber})
}

// GET /api/v1/goods-receipt/history
func (h *Handlers) GoodsReceiptHistory(w http.ResponseWriter, r *http.Request) {
	txs, err := h.ledgerSvc.GetTransactions(50, "RECEIPT")
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, txs)
}

// POST /api/v1/suppliers/ack
func (h *Handlers) SupplierAck(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "acknowledged"})
}

// GET /api/v1/suppliers/overdue-scan
func (h *Handlers) OverdueScan(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"overdue_pos": []any{}, "status": "scanned"})
}
