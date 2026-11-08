from datetime import date, datetime, timedelta
from typing import List, Optional
import numpy as np
import pandas as pd


def prepare_daily_demand_series(
    transactions_df: pd.DataFrame,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> pd.DataFrame:
    """
    Transform raw inventory transaction rows into a continuous daily demand time series.
    Missing dates are filled with zero demand.
    """
    if transactions_df.empty:
        if start_date and end_date:
            all_dates = pd.date_range(start=start_date, end=end_date, freq="D")
            return pd.DataFrame({"ds": all_dates, "y": 0.0})
        return pd.DataFrame(columns=["ds", "y"])

    df = transactions_df.copy()
    df["ds"] = pd.to_datetime(df["created_at"]).dt.date

    # Only include demand events: SALE (negative quantity_delta)
    sales = df[df["transaction_type"] == "SALE"].copy()
    if sales.empty:
        sales = pd.DataFrame({"ds": [datetime.now().date()], "y": [0.0]})
    else:
        sales["y"] = sales["quantity_delta"].abs()

    # Aggregate by date
    daily = sales.groupby("ds")["y"].sum().reset_index()
    daily["ds"] = pd.to_datetime(daily["ds"])

    # Reindex to guarantee continuous day-by-day frequency
    min_date = pd.to_datetime(start_date) if start_date else daily["ds"].min()
    max_date = pd.to_datetime(end_date) if end_date else daily["ds"].max()

    full_idx = pd.date_range(start=min_date, end=max_date, freq="D")
    daily = daily.set_index("ds").reindex(full_idx, fill_value=0.0).reset_index()
    daily.rename(columns={"index": "ds"}, inplace=True)
    daily["y"] = daily["y"].astype(float)
    return daily


def create_ml_features(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract temporal, lag, and rolling statistics features for tree-based forecasting.
    """
    df = daily_df.copy()
    df["dayofweek"] = df["ds"].dt.dayofweek
    df["day"] = df["ds"].dt.day
    df["month"] = df["ds"].dt.month
    df["is_weekend"] = df["dayofweek"].isin([5, 6]).astype(int)

    # Lags
    for lag in [1, 2, 7, 14, 21, 28]:
        df[f"lag_{lag}"] = df["y"].shift(lag)

    # Rolling window statistics (shifted by 1 day to prevent lookahead leakage)
    for window in [7, 14, 30]:
        df[f"rolling_mean_{window}"] = df["y"].shift(1).rolling(window=window, min_periods=1).mean()
        df[f"rolling_std_{window}"] = df["y"].shift(1).rolling(window=window, min_periods=1).std().fillna(0)
        df[f"rolling_max_{window}"] = df["y"].shift(1).rolling(window=window, min_periods=1).max()

    return df

