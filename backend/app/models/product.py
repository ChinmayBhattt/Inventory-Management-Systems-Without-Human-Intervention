from sqlalchemy import Column, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class Product(TimeStampedModel):
    __tablename__ = "products"

    sku = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), index=True, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    default_supplier_id = Column(String(36), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)

    default_supplier = relationship("Supplier", back_populates="products")
    stock_levels = relationship("StockLevel", back_populates="product", cascade="all, delete-orphan")
    transactions = relationship("InventoryTransaction", back_populates="product")
    reorder_policies = relationship("ReorderPolicy", back_populates="product", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")
    po_items = relationship("POItem", back_populates="product")
    alerts = relationship("Alert", back_populates="product")

