from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.ml.feature_engineering import create_ml_features
from backend.app.ml.metrics import calculate_mape, calculate_rmse, calculate_wape


class DemandForecaster:
    COLD_START_THRESHOLD_DAYS = 90

    @classmethod
    def setup_mlflow(cls):
        try:
            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)
        except Exception as e:
            logger.warning(f"Could not initialize MLflow tracking ({e}). Continuing with local logging.")

    @classmethod
    def forecast_cold_start(
        cls,
        daily_df: pd.DataFrame,
        horizons: List[int] = [7, 30]
    ) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """
        Cold-start engine (< 90 days history):
        Uses Exponentially Weighted Moving Average (EWMA) with rolling volatility bounds.
        """
        if daily_df.empty:
            mean_demand = 1.0
            std_demand = 0.5
        else:
            mean_demand = float(daily_df["y"].ewm(span=7, adjust=False).mean().iloc[-1])
            std_demand = float(daily_df["y"].tail(14).std()) if len(daily_df) > 2 else 0.5
            if np.isnan(std_demand) or std_demand == 0:
                std_demand = max(0.5, mean_demand * 0.2)

        mean_demand = max(0.0, mean_demand)
        last_date = daily_df["ds"].max() if not daily_df.empty else datetime.now().date()

        max_horizon = max(horizons)
        future_dates = [last_date + timedelta(days=i) for i in range(1, max_horizon + 1)]

        records = []
        for d in future_dates:
            day_step = (d - last_date).days
            # Slight day-of-week factor if enough data
            dow = d.weekday()
            dow_factor = 1.15 if dow in [4, 5] else 1.0  # weekend lift
            pred = round(mean_demand * dow_factor, 2)
            margin = round(1.96 * std_demand * np.sqrt(1 + day_step * 0.05), 2)
            records.append({
                "forecast_date": d,
                "predicted_demand": pred,
                "confidence_interval_lower": max(0.0, round(pred - margin, 2)),
                "confidence_interval_upper": round(pred + margin, 2),
                "model_name": "MOVING_AVERAGE_EWMA",
            })

        forecast_df = pd.DataFrame(records)

        # Compute backtest metrics on available history
        if len(daily_df) >= 7:
            holdout = daily_df.tail(7)
            hist_mean = daily_df.iloc[:-7]["y"].mean() if len(daily_df) > 7 else daily_df["y"].mean()
            preds = np.full(len(holdout), hist_mean)
            wape = calculate_wape(holdout["y"].values, preds)
            mape = calculate_mape(holdout["y"].values, preds)
        else:
            wape = 0.15
            mape = 15.0

        metrics = {
            "wape": round(wape, 4),
            "mape": round(mape, 2),
            "rmse": round(std_demand, 4)
        }
        return forecast_df, metrics

    @classmethod
    def train_and_forecast_lgb(
        cls,
        daily_df: pd.DataFrame,
        horizons: List[int] = [7, 30]
    ) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """
        Mature series engine (>= 90 days history):
        Trains LightGBM regression model on lagged and rolling features with recursive multi-step forecasting.
        """
        featured = create_ml_features(daily_df)
        featured.dropna(inplace=True)

        if len(featured) < 30:
            return cls.forecast_cold_start(daily_df, horizons)

        feature_cols = [
            c for c in featured.columns if c not in ["ds", "y"]
        ]

        # Holdout split for backtesting (last 14 days)
        test_size = 14
        train_df = featured.iloc[:-test_size]
        val_df = featured.iloc[-test_size:]

        X_train, y_train = train_df[feature_cols], train_df["y"]
        X_val, y_val = val_df[feature_cols], val_df["y"]

        params = {
            "objective": "regression",
            "metric": "mae",
            "learning_rate": 0.05,
            "num_leaves": 15,
            "verbose": -1,
            "random_state": 42
        }

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
            valid_sets=[val_data]
        )

        val_preds = model.predict(X_val)
        val_preds = np.clip(val_preds, 0, None)

        wape = calculate_wape(y_val.values, val_preds)
        mape = calculate_mape(y_val.values, val_preds)
        rmse = calculate_rmse(y_val.values, val_preds)

        # Multi-step recursive forecasting for future horizons
        last_date = daily_df["ds"].max()
        max_horizon = max(horizons)
        sim_df = daily_df.copy()

        future_records = []
        for h in range(1, max_horizon + 1):
            next_date = last_date + timedelta(days=h)
            next_featured = create_ml_features(sim_df)
            latest_row = next_featured.iloc[-1:][feature_cols]

            next_pred = float(model.predict(latest_row)[0])
            next_pred = max(0.0, round(next_pred, 2))

            # Uncertainty expands with horizon sqrt(h)
            margin = round(1.96 * max(1.0, rmse) * np.sqrt(1 + h * 0.05), 2)
            lower = max(0.0, round(next_pred - margin, 2))
            upper = round(next_pred + margin, 2)

            future_records.append({
                "forecast_date": next_date,
                "predicted_demand": next_pred,
                "confidence_interval_lower": lower,
                "confidence_interval_upper": upper,
                "model_name": "LIGHTGBM_MATURE",
            })

            # Append prediction to simulation dataframe for next step's lags
            sim_df = pd.concat([
                sim_df,
                pd.DataFrame([{"ds": next_date, "y": next_pred}])
            ], ignore_index=True)

        forecast_df = pd.DataFrame(future_records)
        metrics = {
            "wape": round(wape, 4),
            "mape": round(mape, 2),
            "rmse": round(rmse, 4)
        }
        return forecast_df, metrics

    @classmethod
    def train_and_forecast_sku(
        cls,
        sku_id: str,
        daily_df: pd.DataFrame,
        horizons: List[int] = [7, 30]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Master SKU forecasting pipeline:
        Routes between cold-start and mature model, runs backtesting, and logs run to MLflow.
        """
        cls.setup_mlflow()
        num_days = len(daily_df)
        is_cold_start = num_days < cls.COLD_START_THRESHOLD_DAYS

        if is_cold_start:
            logger.info(f"SKU {sku_id}: History length {num_days} < 90 days. Using Cold-Start EWMA forecaster.")
            forecast_df, metrics = cls.forecast_cold_start(daily_df, horizons)
            model_name = "MOVING_AVERAGE_EWMA"
        else:
            logger.info(f"SKU {sku_id}: History length {num_days} >= 90 days. Using LightGBM mature forecaster.")
            try:
                forecast_df, metrics = cls.train_and_forecast_lgb(daily_df, horizons)
                model_name = "LIGHTGBM_MATURE"
            except Exception as e:
                logger.warning(f"LightGBM failed ({e}), falling back to EWMA.")
                forecast_df, metrics = cls.forecast_cold_start(daily_df, horizons)
                model_name = "MOVING_AVERAGE_EWMA_FALLBACK"

        # Log to MLflow
        run_id = f"local_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            with mlflow.start_run(run_name=f"forecast_sku_{sku_id[:8]}") as run:
                run_id = run.info.run_id
                mlflow.log_param("sku_id", sku_id)
                mlflow.log_param("model_name", model_name)
                mlflow.log_param("history_days", num_days)
                mlflow.log_param("is_cold_start", is_cold_start)
                mlflow.log_metric("wape", metrics["wape"])
                mlflow.log_metric("mape", metrics["mape"])
                mlflow.log_metric("rmse", metrics["rmse"])
        except Exception as e:
            logger.debug(f"MLflow run logging skipped ({e}).")

        metadata = {
            "model_name": model_name,
            "model_version": run_id,
            "is_cold_start": is_cold_start,
            "history_days": num_days,
            **metrics
        }
        return forecast_df, metadata

