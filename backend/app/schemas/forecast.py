from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


class ForecastPoint(BaseModel):
    forecast_date: date
    horizon_days: int
    predicted_demand: float
    confidence_interval_lower: Optional[float] = None
    confidence_interval_upper: Optional[float] = None
    model_name: str
    model_version: Optional[str] = None
    backtest_wape: Optional[float] = None
    backtest_mape: Optional[float] = None


class ForecastResponse(BaseModel):
    product_id: str
    warehouse_id: str
    model_name: str
    model_version: Optional[str] = None
    is_cold_start: bool
    backtest_wape: Optional[float] = None
    backtest_mape: Optional[float] = None
    tactical_7d_total: float
    strategic_30d_total: float
    daily_forecasts: List[ForecastPoint]


class ActualVsPredictedPoint(BaseModel):
    date: date
    actual_demand: float
    predicted_demand: Optional[float] = None
    confidence_interval_lower: Optional[float] = None
    confidence_interval_upper: Optional[float] = None


class ActualVsPredictedResponse(BaseModel):
    product_id: str
    warehouse_id: str
    points: List[ActualVsPredictedPoint]

