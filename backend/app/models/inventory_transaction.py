from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Index
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class InventoryTransaction(TimeStampedModel):
    __tablename__ = "inventory_transactions"

    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Types: SALE, RECEIPT, RETURN, DAMAGE, ADJUSTMENT, TRANSFER
    transaction_type = Column(String(50), nullable=False, index=True)
    
    # Positive for additions (RECEIPT, RETURN, positive ADJUSTMENT), Negative for deductions (SALE, DAMAGE)
    quantity_delta = Column(Integer, nullable=False)
    
    reference_type = Column(String(50), nullable=False, index=True)  # ORDER, PURCHASE_ORDER, MANUAL, SYSTEM
    reference_id = Column(String(255), nullable=True, index=True)
    
    idempotency_key = Column(String(255), unique=True, index=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    product = relationship("Product", back_populates="transactions")
    warehouse = relationship("Warehouse", back_populates="transactions")

    __table_args__ = (
        Index("idx_inv_trans_product_wh", "product_id", "warehouse_id", "created_at"),
    )

