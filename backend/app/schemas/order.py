from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)


class OrderItemResponse(BaseModel):
    id: str
    order_id: str
    product_id: str
    quantity: int
    unit_price: Decimal

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    order_number: str
    warehouse_id: str
    items: List[OrderItemCreate]
    idempotency_key: str
    channel: str = "REST_API"


class OrderResponse(BaseModel):
    id: str
    order_number: str
    channel: str
    status: str
    idempotency_key: str
    warehouse_id: str
    total_amount: Decimal
    items: List[OrderItemResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class ShopifyLineItem(BaseModel):
    id: int
    title: Optional[str] = None
    sku: Optional[str] = None
    quantity: int
    price: str


class ShopifyWebhookPayload(BaseModel):
    id: int
    name: Optional[str] = None
    created_at: Optional[str] = None
    total_price: Optional[str] = "0.00"
    line_items: List[ShopifyLineItem] = []

