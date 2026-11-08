from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class Order(TimeStampedModel):
    __tablename__ = "orders"

    order_number = Column(String(100), unique=True, index=True, nullable=False)
    channel = Column(String(50), default="REST_API", nullable=False)  # REST_API, SHOPIFY_WEBHOOK, etc.
    status = Column(String(50), default="PENDING", nullable=False)    # PENDING, RESERVED, FULFILLED, CANCELLED
    idempotency_key = Column(String(255), unique=True, index=True, nullable=False)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    total_amount = Column(Numeric(12, 2), default=0.00, nullable=False)

    warehouse = relationship("Warehouse", lazy="selectin")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class OrderItem(TimeStampedModel):
    __tablename__ = "order_items"

    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

