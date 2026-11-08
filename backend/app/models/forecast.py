from sqlalchemy import Column, Date, Float, ForeignKey, Integer, Numeric, String, Index
from sqlalchemy.orm import relationship
from backend.app.models.base import TimeStampedModel


class Forecast(TimeStampedModel):
    __tablename__ = "forecasts"

    product_id = Column(String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    
    forecast_date = Column(Date, nullable=False, index=True)
    horizon_days = Column(Integer, nullable=False)  # 7 or 30
    predicted_demand = Column(Float, nullable=False)
    confidence_interval_lower = Column(Float, nullable=True)
    confidence_interval_upper = Column(Float, nullable=True)
    
    model_name = Column(String(50), nullable=False)     # PROPHET, XGBOOST, LIGHTGBM, MOVING_AVERAGE
    model_version = Column(String(100), nullable=True)   # MLflow Run ID or version string
    backtest_wape = Column(Float, nullable=True)         # Weighted Absolute Percentage Error
    backtest_mape = Column(Float, nullable=True)         # Mean Absolute Percentage Error

    product = relationship("Product", back_populates="forecasts")
    warehouse = relationship("Warehouse")

    __table_args__ = (
        Index("idx_forecast_sku_wh_date", "product_id", "warehouse_id", "forecast_date", "horizon_days"),
    )

