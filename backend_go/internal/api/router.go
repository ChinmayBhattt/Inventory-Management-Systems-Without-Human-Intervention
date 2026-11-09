package api

import (
	"net/http"
)

func NewRouter(h *Handlers) http.Handler {
	mux := http.NewServeMux()

	// Health
	mux.HandleFunc("GET /health", h.Health)

	// Auth
	mux.HandleFunc("POST /api/v1/auth/login", h.Login)

	// Ledger
	mux.HandleFunc("GET /api/v1/ledger/stock-levels", h.GetStockLevels)
	mux.HandleFunc("GET /api/v1/ledger/transactions", h.GetTransactions)

	// Orders & Webhooks
	mux.HandleFunc("POST /api/v1/orders/create", h.CreateOrder)
	mux.HandleFunc("POST /api/v1/orders/webhook/shopify", h.ShopifyWebhook)

	// Purchase Orders (both with and without trailing slash)
	mux.HandleFunc("GET /api/v1/purchase-orders", h.ListPurchaseOrders)
	mux.HandleFunc("GET /api/v1/purchase-orders/", h.ListPurchaseOrders)
	mux.HandleFunc("POST /api/v1/purchase-orders/{id}/approve", h.ApprovePurchaseOrder)

	// Alerts (both with and without trailing slash)
	mux.HandleFunc("GET /api/v1/alerts", h.ListAlerts)
	mux.HandleFunc("GET /api/v1/alerts/", h.ListAlerts)
	mux.HandleFunc("POST /api/v1/alerts/{id}/resolve", h.ResolveAlert)
	mux.HandleFunc("POST /api/v1/alerts/audit", h.AuditStockDrift)

	// Replenishment
	mux.HandleFunc("GET /api/v1/replenishment/policies", h.GetPolicies)
	mux.HandleFunc("PUT /api/v1/replenishment/policies/{id}", h.UpdatePolicy)
	mux.HandleFunc("POST /api/v1/replenishment/evaluate", h.EvaluateReplenishment)

	// Forecasts
	mux.HandleFunc("GET /api/v1/forecasts/evaluation", h.ForecastEvaluation)
	mux.HandleFunc("GET /api/v1/forecasts/timeline", h.ForecastTimeline)

	// Goods Receipt
	mux.HandleFunc("POST /api/v1/goods-receipt/receive", h.ReceiveGoods)
	mux.HandleFunc("GET /api/v1/goods-receipt/history", h.GoodsReceiptHistory)

	// Suppliers
	mux.HandleFunc("POST /api/v1/suppliers/ack", h.SupplierAck)
	mux.HandleFunc("GET /api/v1/suppliers/overdue-scan", h.OverdueScan)

	// Wrap with Middleware
	handler := CORSMiddleware(mux)
	handler = LoggingAndTimingMiddleware(handler)

	return handler
}

