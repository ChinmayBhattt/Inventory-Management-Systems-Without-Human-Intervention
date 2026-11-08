from fastapi import APIRouter
from backend.app.api.v1.endpoints import (
    alerts,
    auth,
    forecasts,
    goods_receipt,
    ledger,
    orders,
    purchase_orders,
    replenishment,
    suppliers,
)

api_router = APIRouter()

# Authentication & Users
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Inventory Ledger & Stock Levels
api_router.include_router(ledger.router, prefix="/ledger", tags=["Inventory Ledger"])

# Order Ingestion & Webhooks
api_router.include_router(orders.router, prefix="/orders", tags=["Order Ingestion"])

# Demand Forecasting & MLflow Registry
api_router.include_router(forecasts.router, prefix="/forecasts", tags=["Demand Forecasting"])

# Stochastic Replenishment Engine
api_router.include_router(replenishment.router, prefix="/replenishment", tags=["Replenishment Engine"])

# Purchase Orders & Auto-Approval
api_router.include_router(purchase_orders.router, prefix="/purchase-orders", tags=["Purchase Orders"])

# Supplier Gateway & Acknowledgment
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["Supplier Gateway"])

# Goods Receipt Note (GRN) Ingestion
api_router.include_router(goods_receipt.router, prefix="/goods-receipt", tags=["Goods Receipt"])

# Exception & Anomaly Alerts Feed
api_router.include_router(alerts.router, prefix="/alerts", tags=["Exception & Anomaly Alerts"])


