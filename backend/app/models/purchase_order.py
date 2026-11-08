from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class PurchaseOrder(TimeStampedModel):
    __tablename__ = "purchase_orders"

    po_number = Column(String(100), unique=True, index=True, nullable=False)
    supplier_id = Column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    # Statuses: DRAFT, AUTO_APPROVED, NEEDS_REVIEW, SENT, CONFIRMED, PARTIALLY_RECEIVED, COMPLETED, CANCELLED
    status = Column(String(50), default="DRAFT", nullable=False, index=True)
    approval_mode = Column(String(50), default="AUTONOMOUS", nullable=False)  # AUTONOMOUS, MANUAL
    total_cost = Column(Numeric(12, 2), default=0.00, nullable=False)
    
    expected_delivery_date = Column(DateTime(timezone=True), nullable=True)
    confirmed_delivery_date = Column(DateTime(timezone=True), nullable=True)
    
    pdf_storage_path = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    supplier = relationship("Supplier", back_populates="purchase_orders", lazy="selectin")
    warehouse = relationship("Warehouse", lazy="selectin")
    items = relationship("POItem", back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin")


class POItem(TimeStampedModel):
    __tablename__ = "po_items"

    po_id = Column(String(36), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_received = Column(Integer, default=0, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product", back_populates="po_items")

