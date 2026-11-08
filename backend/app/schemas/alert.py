from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    product_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    message: str
    context_data: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertResolveRequest(BaseModel):
    resolution_notes: Optional[str] = None


class AnomalyAuditItem(BaseModel):
    category: str
    severity: str
    entity_id: str
    detail: str


class AnomalyAuditResponse(BaseModel):
    total_anomalies_detected: int
    stock_drift_count: int
    demand_spike_count: int
    dead_stock_count: int
    supplier_delay_count: int
    audited_at: datetime
    anomalies: List[AnomalyAuditItem]

