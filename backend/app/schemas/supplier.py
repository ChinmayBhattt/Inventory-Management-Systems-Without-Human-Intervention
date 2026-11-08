from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class SupplierBase(BaseModel):
    name: str
    email: EmailStr
    api_endpoint: Optional[str] = None
    lead_time_days: int = Field(7, ge=1)
    minimum_order_value: Decimal = Field(Decimal("0.00"), ge=0)
    reliability_score: float = Field(1.0, ge=0.0, le=1.0)


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class POAcknowledgmentRequest(BaseModel):
    po_number: str
    confirmed_delivery_date: datetime
    tracking_number: Optional[str] = None
    notes: Optional[str] = None


class PODispatchResponse(BaseModel):
    po_number: str
    dispatched_via: str  # REST_API, EMAIL, or MOCK
    destination: str
    status: str
    dispatched_at: datetime

