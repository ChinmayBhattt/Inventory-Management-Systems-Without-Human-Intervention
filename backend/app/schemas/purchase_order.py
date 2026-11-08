from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class POItemResponse(BaseModel):
    id: str
    product_id: str
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal

    class Config:
        from_attributes = True


class PurchaseOrderResponse(BaseModel):
    id: str
    po_number: str
    supplier_id: str
    warehouse_id: str
    status: str
    approval_mode: str
    total_cost: Decimal
    expected_delivery_date: Optional[datetime] = None
    confirmed_delivery_date: Optional[datetime] = None
    pdf_storage_path: Optional[str] = None
    notes: Optional[str] = None
    items: List[POItemResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class POApprovalRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Optional approval notes from human manager")

