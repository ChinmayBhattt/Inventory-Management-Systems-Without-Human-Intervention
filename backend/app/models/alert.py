from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class Alert(TimeStampedModel):
    __tablename__ = "alerts"

    # Alert types: STOCK_DRIFT, DEMAND_SPIKE, DEAD_STOCK, NEGATIVE_STOCK, SUPPLIER_DELAY, PO_NEEDS_REVIEW
    alert_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="WARNING", nullable=False, index=True) # CRITICAL, WARNING, INFO
    
    product_id = Column(String(36), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True)
    
    message = Column(Text, nullable=False)
    context_data = Column(JSON, nullable=True)
    status = Column(String(20), default="OPEN", nullable=False, index=True)      # OPEN, ACKNOWLEDGED, RESOLVED
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    product = relationship("Product", back_populates="alerts")
    warehouse = relationship("Warehouse")

