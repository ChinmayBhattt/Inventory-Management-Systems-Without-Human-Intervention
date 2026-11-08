from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.user import User
from backend.app.models.warehouse import Warehouse
from backend.app.schemas.forecast import ActualVsPredictedResponse, ForecastResponse
from backend.app.services.forecast_service import ForecastService

router = APIRouter()


@router.post("/{product_id}/train", response_model=ForecastResponse)
async def train_and_forecast_sku(
    product_id: str,
    warehouse_id: Optional[str] = Query(None, description="Optional warehouse ID"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    Trigger demand forecast model training, backtesting, and MLflow logging for a SKU.
    """
    if not warehouse_id:
        wh_res = await db.execute(select(Warehouse).where(Warehouse.is_active == True).limit(1))
        wh = wh_res.scalar_one_or_none()
        warehouse_id = wh.id if wh else None

    return await ForecastService.generate_and_save_forecast(
        db=db,
        product_id=product_id,
        warehouse_id=warehouse_id
    )


@router.get("/{product_id}", response_model=ForecastResponse)
async def get_forecast(
    product_id: str,
    warehouse_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve current 7-day tactical and 30-day strategic demand forecasts with confidence intervals.
    """
    if not warehouse_id:
        wh_res = await db.execute(select(Warehouse).where(Warehouse.is_active == True).limit(1))
        wh = wh_res.scalar_one_or_none()
        warehouse_id = wh.id if wh else None

    return await ForecastService.get_sku_forecasts(
        db=db,
        product_id=product_id,
        warehouse_id=warehouse_id
    )


@router.get("/{product_id}/actual-vs-predicted", response_model=ActualVsPredictedResponse)
async def get_actual_vs_predicted_series(
    product_id: str,
    warehouse_id: Optional[str] = Query(None),
    history_days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve unified time series of actual sales vs predicted demand with confidence bounds for Recharts.
    """
    if not warehouse_id:
        wh_res = await db.execute(select(Warehouse).where(Warehouse.is_active == True).limit(1))
        wh = wh_res.scalar_one_or_none()
        warehouse_id = wh.id if wh else None

    return await ForecastService.get_actual_vs_predicted(
        db=db,
        product_id=product_id,
        warehouse_id=warehouse_id,
        history_days=history_days
    )

