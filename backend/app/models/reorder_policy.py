from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class ReorderPolicy(TimeStampedModel):
    __tablename__ = "reorder_policies"

    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)

    # Replenishment Parameters
    service_level_z = Column(Float, default=1.65, nullable=False)        # 95% service level = 1.65
    lead_time_days = Column(Integer, default=7, nullable=False)
    holding_cost_annual_pct = Column(Float, default=0.20, nullable=False) # 20% per year
    fixed_order_cost = Column(Numeric(12, 2), default=50.00, nullable=False)
    
    # Computed Dynamic Targets
    safety_stock = Column(Integer, default=0, nullable=False)
    reorder_point = Column(Integer, default=0, nullable=False)
    economic_order_quantity = Column(Integer, default=10, nullable=False)
    
    # Autonomy Guardrails
    auto_approve_max_po_value = Column(Numeric(12, 2), default=5000.00, nullable=False)
    is_autonomous = Column(Boolean, default=True, nullable=False)

    product = relationship("Product", back_populates="reorder_policies")
    warehouse = relationship("Warehouse")

    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_reorder_policy_product_warehouse"),
    )

