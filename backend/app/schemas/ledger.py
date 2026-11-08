from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    product_id: str
    warehouse_id: str
    transaction_type: str = Field(..., description="SALE, RECEIPT, RETURN, DAMAGE, ADJUSTMENT, TRANSFER")
    quantity_delta: int = Field(..., description="Positive for credit, negative for debit")
    reference_type: str = Field(..., description="ORDER, PURCHASE_ORDER, MANUAL, SYSTEM")
    reference_id: Optional[str] = None
    idempotency_key: str
    metadata_json: Optional[Dict[str, Any]] = None


class TransactionResponse(BaseModel):
    id: str
    product_id: str
    warehouse_id: str
    transaction_type: str
    quantity_delta: int
    reference_type: str
    reference_id: Optional[str] = None
    idempotency_key: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StockLevelResponse(BaseModel):
    id: str
    product_id: str
    warehouse_id: str
    on_hand: int
    reserved: int
    on_order: int
    available: int
    last_reconciled_at: datetime

    class Config:
        from_attributes = True


class AdjustmentRequest(BaseModel):
    product_id: str
    warehouse_id: str
    quantity_delta: int
    adjustment_type: str = Field("ADJUSTMENT", description="ADJUSTMENT, DAMAGE, RETURN")
    reason: str
    idempotency_key: str


class ReconciliationResponse(BaseModel):
    product_id: str
    warehouse_id: str
    cached_on_hand: int
    ledger_sum_on_hand: int
    discrepancy: int
    is_synchronized: bool
    reconciled_at: datetime

