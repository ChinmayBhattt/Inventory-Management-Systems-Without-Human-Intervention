from sqlalchemy import Column, Float, Integer, Numeric, String
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class Supplier(TimeStampedModel):
    __tablename__ = "suppliers"

    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    api_endpoint = Column(String(500), nullable=True)
    lead_time_days = Column(Integer, default=7, nullable=False)
    minimum_order_value = Column(Numeric(12, 2), default=0.00, nullable=False)
    reliability_score = Column(Float, default=1.00, nullable=False)  # 0.0 to 1.0

    products = relationship("Product", back_populates="default_supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")

