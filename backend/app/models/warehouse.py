from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class Warehouse(TimeStampedModel):
    __tablename__ = "warehouses"

    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    stock_levels = relationship("StockLevel", back_populates="warehouse", cascade="all, delete-orphan")
    transactions = relationship("InventoryTransaction", back_populates="warehouse")

