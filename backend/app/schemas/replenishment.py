from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class ReorderPolicyBase(BaseModel):
    service_level_z: float = Field(1.65, description="Z factor: 1.65 for 95%, 2.33 for 99%")
    lead_time_days: int = Field(7, ge=1)
    holding_cost_annual_pct: float = Field(0.20, gt=0.0)
    fixed_order_cost: Decimal = Field(Decimal("50.00"), ge=0)
    auto_approve_max_po_value: Decimal = Field(Decimal("5000.00"), ge=0)
    is_autonomous: bool = True


class ReorderPolicyCreate(ReorderPolicyBase):
    product_id: str
    warehouse_id: str


class ReorderPolicyUpdate(BaseModel):
    service_level_z: Optional[float] = None
    lead_time_days: Optional[int] = None
    holding_cost_annual_pct: Optional[float] = None
    fixed_order_cost: Optional[Decimal] = None
    auto_approve_max_po_value: Optional[Decimal] = None
    is_autonomous: Optional[bool] = None


class ReorderPolicyResponse(ReorderPolicyBase):
    id: str
    product_id: str
    warehouse_id: str
    safety_stock: int
    reorder_point: int
    economic_order_quantity: int
    updated_at: datetime

    class Config:
        from_attributes = True


class ReplenishmentEvaluationItem(BaseModel):
    product_id: str
    sku: str
    warehouse_id: str
    on_hand: int
    on_order: int
    reserved: int
    effective_stock: int
    reorder_point: int
    economic_order_quantity: int
    is_triggered: bool
    recommended_order_quantity: int
    po_generated: bool
    po_number: Optional[str] = None
    po_status: Optional[str] = None
    estimated_cost: Decimal = Decimal("0.00")


class ReplenishmentRunResponse(BaseModel):
    evaluated_skus: int
    triggered_skus: int
    purchase_orders_created: int
    total_spend_committed: Decimal
    items: List[ReplenishmentEvaluationItem]

