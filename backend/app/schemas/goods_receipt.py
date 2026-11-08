from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class GoodsReceiptItem(BaseModel):
    product_id: str
    quantity_received: int = Field(..., gt=0)
    condition: str = Field("GOOD", description="GOOD or DAMAGED")
    lot_number: Optional[str] = None


class GoodsReceiptRequest(BaseModel):
    po_number: str
    warehouse_id: str
    grn_number: Optional[str] = None
    items: List[GoodsReceiptItem]
    notes: Optional[str] = None


class ReceivedItemResult(BaseModel):
    product_id: str
    quantity_received: int
    condition: str
    transaction_id: str
    new_on_hand: int
    new_on_order: int


class GoodsReceiptResponse(BaseModel):
    grn_number: str
    po_number: str
    po_status: str  # PARTIALLY_RECEIVED or COMPLETED
    warehouse_id: str
    items_received: List[ReceivedItemResult]
    received_at: datetime

