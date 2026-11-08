from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
import pandas as pd
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.logging import logger
from backend.app.ml.feature_engineering import prepare_daily_demand_series
from backend.app.ml.forecaster import DemandForecaster
from backend.app.models.forecast import Forecast
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.product import Product
from backend.app.models.warehouse import Warehouse
from backend.app.schemas.forecast import (
    ActualVsPredictedPoint,
    ActualVsPredictedResponse,
    ForecastPoint,
    ForecastResponse,
)


class ForecastService:
    @staticmethod
    async def generate_and_save_forecast(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str
    ) -> ForecastResponse:
        """
        Pull transactions, run appropriate forecasting model, store in database, and return results.
        """
        # Validate product and warehouse
        p_res = await db.execute(select(Product).where(Product.id == product_id))
        product = p_res.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

        w_res = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
        warehouse = w_res.scalar_one_or_none()
        if not warehouse:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

        # 1. Fetch transactions
        stmt = select(InventoryTransaction).where(
            InventoryTransaction.product_id == product_id,
            InventoryTransaction.warehouse_id == warehouse_id
        ).order_by(InventoryTransaction.created_at.asc())
        t_res = await db.execute(stmt)
        txs = t_res.scalars().all()

        # Convert to DataFrame
        tx_data = [
            {
                "created_at": tx.created_at,
                "transaction_type": tx.transaction_type,
                "quantity_delta": tx.quantity_delta
            }
            for tx in txs
        ]
        tx_df = pd.DataFrame(tx_data)

        # 2. Prepare continuous daily time series
        daily_df = prepare_daily_demand_series(tx_df)

        # 3. Generate forecasts
        forecast_df, meta = DemandForecaster.train_and_forecast_sku(
            sku_id=product.sku,
            daily_df=daily_df,
            horizons=[7, 30]
        )

        # 4. Clean out existing future forecasts for this SKU and WH to prevent duplicate historical predictions
        today = datetime.now(timezone.utc).date()
        del_stmt = delete(Forecast).where(
            Forecast.product_id == product_id,
            Forecast.warehouse_id == warehouse_id,
            Forecast.forecast_date >= today
        )
        await db.execute(del_stmt)

        # 5. Insert new forecast points
        forecast_points = []
        tactical_7d = 0.0
        strategic_30d = 0.0

        for idx, row in forecast_df.iterrows():
            raw_date = row["forecast_date"]
            f_date = raw_date.date() if hasattr(raw_date, "date") else raw_date
            horizon = (f_date - today).days
            pred_demand = float(row["predicted_demand"])

            if horizon <= 7:
                tactical_7d += pred_demand
            if horizon <= 30:
                strategic_30d += pred_demand

            fc_entry = Forecast(
                product_id=product_id,
                warehouse_id=warehouse_id,
                forecast_date=f_date,
                horizon_days=horizon,
                predicted_demand=pred_demand,
                confidence_interval_lower=row.get("confidence_interval_lower"),
                confidence_interval_upper=row.get("confidence_interval_upper"),
                model_name=meta["model_name"],
                model_version=meta.get("model_version"),
                backtest_wape=meta.get("wape"),
                backtest_mape=meta.get("mape"),
            )
            db.add(fc_entry)

            forecast_points.append(
                ForecastPoint(
                    forecast_date=f_date,
                    horizon_days=horizon,
                    predicted_demand=pred_demand,
                    confidence_interval_lower=row.get("confidence_interval_lower"),
                    confidence_interval_upper=row.get("confidence_interval_upper"),
                    model_name=meta["model_name"],
                    model_version=meta.get("model_version"),
                    backtest_wape=meta.get("wape"),
                    backtest_mape=meta.get("mape"),
                )
            )

        await db.commit()

        logger.info(
            f"Forecast refreshed for SKU {product.sku}. Tactical 7d: {tactical_7d:.1f}, "
            f"Strategic 30d: {strategic_30d:.1f}, Model: {meta['model_name']}"
        )

        return ForecastResponse(
            product_id=product_id,
            warehouse_id=warehouse_id,
            model_name=meta["model_name"],
            model_version=meta.get("model_version"),
            is_cold_start=meta["is_cold_start"],
            backtest_wape=meta.get("wape"),
            backtest_mape=meta.get("mape"),
            tactical_7d_total=round(tactical_7d, 2),
            strategic_30d_total=round(strategic_30d, 2),
            daily_forecasts=forecast_points
        )

    @staticmethod
    async def get_sku_forecasts(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str
    ) -> ForecastResponse:
        """Fetch latest stored forecasts for a SKU."""
        today = datetime.now(timezone.utc).date()
        stmt = select(Forecast).where(
            Forecast.product_id == product_id,
            Forecast.warehouse_id == warehouse_id,
            Forecast.forecast_date >= today
        ).order_by(Forecast.forecast_date.asc())

        res = await db.execute(stmt)
        entries = res.scalars().all()

        if not entries:
            # If no cached forecast, generate immediately
            return await ForecastService.generate_and_save_forecast(db, product_id, warehouse_id)

        first = entries[0]
        points = [
            ForecastPoint(
                forecast_date=e.forecast_date,
                horizon_days=e.horizon_days,
                predicted_demand=e.predicted_demand,
                confidence_interval_lower=e.confidence_interval_lower,
                confidence_interval_upper=e.confidence_interval_upper,
                model_name=e.model_name,
                model_version=e.model_version,
                backtest_wape=e.backtest_wape,
                backtest_mape=e.backtest_mape
            )
            for e in entries
        ]

        tactical_7d = sum(p.predicted_demand for p in points if p.horizon_days <= 7)
        strategic_30d = sum(p.predicted_demand for p in points if p.horizon_days <= 30)

        return ForecastResponse(
            product_id=product_id,
            warehouse_id=warehouse_id,
            model_name=first.model_name,
            model_version=first.model_version,
            is_cold_start="COLD" in first.model_name or "EWMA" in first.model_name,
            backtest_wape=first.backtest_wape,
            backtest_mape=first.backtest_mape,
            tactical_7d_total=round(tactical_7d, 2),
            strategic_30d_total=round(strategic_30d, 2),
            daily_forecasts=points
        )

    @staticmethod
    async def get_actual_vs_predicted(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        history_days: int = 30
    ) -> ActualVsPredictedResponse:
        """
        Produce a unified timeline aligning actual historical sales against forecasts for charting.
        """
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=history_days)

        # 1. Fetch transactions in window
        stmt = select(InventoryTransaction).where(
            InventoryTransaction.product_id == product_id,
            InventoryTransaction.warehouse_id == warehouse_id,
            InventoryTransaction.created_at >= start_date
        ).order_by(InventoryTransaction.created_at.asc())
        t_res = await db.execute(stmt)
        txs = t_res.scalars().all()

        tx_data = [
            {
                "created_at": tx.created_at,
                "transaction_type": tx.transaction_type,
                "quantity_delta": tx.quantity_delta
            }
            for tx in txs
        ]
        daily_df = prepare_daily_demand_series(pd.DataFrame(tx_data), start_date=start_date, end_date=end_date)
        actual_map = {row["ds"].date() if hasattr(row["ds"], "date") else row["ds"]: row["y"] for _, row in daily_df.iterrows()}

        # 2. Fetch future/current forecasts
        f_stmt = select(Forecast).where(
            Forecast.product_id == product_id,
            Forecast.warehouse_id == warehouse_id,
            Forecast.forecast_date >= start_date
        ).order_by(Forecast.forecast_date.asc())
        f_res = await db.execute(f_stmt)
        forecasts = f_res.scalars().all()
        forecast_map = {f.forecast_date: f for f in forecasts}

        # Build timeline from start_date to end_date + 30 days
        all_dates = pd.date_range(start=start_date, end=end_date + timedelta(days=30), freq="D")
        points = []

        for dt in all_dates:
            d = dt.date()
            act = actual_map.get(d, 0.0) if d <= end_date else 0.0
            fc = forecast_map.get(d)
            pred = fc.predicted_demand if fc else None
            lower = fc.confidence_interval_lower if fc else None
            upper = fc.confidence_interval_upper if fc else None

            points.append(
                ActualVsPredictedPoint(
                    date=d,
                    actual_demand=float(act) if d <= end_date else 0.0,
                    predicted_demand=pred,
                    confidence_interval_lower=lower,
                    confidence_interval_upper=upper
                )
            )

        return ActualVsPredictedResponse(
            product_id=product_id,
            warehouse_id=warehouse_id,
            points=points
        )
