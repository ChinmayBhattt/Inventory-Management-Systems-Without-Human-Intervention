from datetime import datetime, timedelta, timezone
import uuid
import numpy as np
import pandas as pd
import pytest
from backend.app.core.security import create_access_token
from backend.app.ml.feature_engineering import create_ml_features, prepare_daily_demand_series
from backend.app.ml.forecaster import DemandForecaster
from backend.app.ml.metrics import calculate_mape, calculate_rmse, calculate_wape
from backend.app.models.product import Product
from backend.app.models.user import User
from backend.app.models.warehouse import Warehouse
from backend.app.services.ledger_service import InventoryLedgerService


@pytest.fixture
async def auth_headers(db_session):
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"forecaster_{user_id[:8]}@example.com",
        hashed_password="hash",
        full_name="Forecaster Admin",
        role="admin",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(subject=user.id, role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_wape_and_mape_metrics():
    """Verify exact formula execution for WAPE and MAPE."""
    actual = np.array([10.0, 20.0, 30.0, 0.0])
    predicted = np.array([12.0, 18.0, 33.0, 2.0])

    # sum(|actual - predicted|) = 2 + 2 + 3 + 2 = 9
    # sum(actual) = 60
    # WAPE = 9 / 60 = 0.15
    wape = calculate_wape(actual, predicted)
    assert abs(wape - 0.15) < 1e-4

    # Perfect forecast
    assert calculate_wape(actual, actual) == 0.0
    assert calculate_mape(actual, actual) == 0.0

    # Zero actuals edge case
    zero_actual = np.array([0.0, 0.0])
    zero_pred = np.array([0.0, 0.0])
    assert calculate_wape(zero_actual, zero_pred) == 0.0

    # Non-zero pred on zero actuals
    assert calculate_wape(zero_actual, np.array([5.0, 5.0])) == 1.0


def test_cold_start_forecasting_pipeline():
    """Verify cold start (< 90 days) triggers EWMA and produces dual horizons."""
    dates = pd.date_range(end=datetime.now().date(), periods=45, freq="D")
    y = np.random.poisson(lam=15, size=45).astype(float)
    df = pd.DataFrame({"ds": dates, "y": y})

    forecast_df, meta = DemandForecaster.train_and_forecast_sku(
        sku_id="COLD_SKU_1",
        daily_df=df,
        horizons=[7, 30]
    )

    assert meta["is_cold_start"] is True
    assert "EWMA" in meta["model_name"]
    assert len(forecast_df) == 30
    assert "predicted_demand" in forecast_df.columns
    assert "confidence_interval_lower" in forecast_df.columns
    assert "confidence_interval_upper" in forecast_df.columns

    # Invariant: upper bound >= predicted >= lower bound >= 0
    assert (forecast_df["predicted_demand"] >= forecast_df["confidence_interval_lower"]).all()
    assert (forecast_df["confidence_interval_upper"] >= forecast_df["predicted_demand"]).all()
    assert (forecast_df["confidence_interval_lower"] >= 0).all()


def test_mature_series_forecasting_pipeline():
    """Verify mature series (>= 90 days) triggers LightGBM with backtesting metrics."""
    # Generate 120 days of synthetic sales with weekly seasonality
    dates = pd.date_range(end=datetime.now().date(), periods=120, freq="D")
    base = 25.0
    seasonality = np.sin(np.linspace(0, 10 * np.pi, 120)) * 5
    noise = np.random.normal(0, 2, 120)
    y = np.clip(base + seasonality + noise, 0, None)

    df = pd.DataFrame({"ds": dates, "y": y})

    forecast_df, meta = DemandForecaster.train_and_forecast_sku(
        sku_id="MATURE_SKU_1",
        daily_df=df,
        horizons=[7, 30]
    )

    assert meta["is_cold_start"] is False
    assert meta["model_name"] == "LIGHTGBM_MATURE"
    assert "wape" in meta
    assert "mape" in meta
    assert meta["wape"] >= 0.0
    assert len(forecast_df) == 30


@pytest.mark.asyncio
async def test_forecast_api_endpoints(async_client, db_session, auth_headers):
    """Test forecast training and actual vs predicted retrieval endpoints."""
    wh = Warehouse(code=f"WH_{uuid.uuid4().hex[:6]}", name="Forecast WH", is_active=True)
    prod = Product(
        sku=f"SKU_FC_{uuid.uuid4().hex[:6]}",
        name="Predictable Widget",
        category="Office",
        unit_cost=10.00,
        unit_price=20.00
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # Seed initial 500 units stock
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod.id,
        warehouse_id=wh.id,
        transaction_type="RECEIPT",
        quantity_delta=500,
        reference_type="PO",
        reference_id="PO-INIT-FC",
        idempotency_key=f"tx_init_{uuid.uuid4()}"
    )

    # Seed 15 days of transactions
    now = datetime.now(timezone.utc)
    for i in range(15):
        tx_date = now - timedelta(days=15 - i)
        await InventoryLedgerService.record_transaction(
            db=db_session,
            product_id=prod.id,
            warehouse_id=wh.id,
            transaction_type="SALE",
            quantity_delta=-10,
            reference_type="ORDER",
            reference_id=f"ORD-SIM-{i}",
            idempotency_key=f"tx_fc_{uuid.uuid4()}",
            metadata_json={"sim_date": tx_date.isoformat()}
        )
    await db_session.commit()

    # 1. Trigger training endpoint
    train_resp = await async_client.post(
        f"/api/v1/forecasts/{prod.id}/train?warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert train_resp.status_code == 200
    fc_data = train_resp.json()
    assert fc_data["product_id"] == prod.id
    assert fc_data["tactical_7d_total"] > 0
    assert fc_data["strategic_30d_total"] > 0
    assert len(fc_data["daily_forecasts"]) == 30

    # 2. Get stored forecast
    get_resp = await async_client.get(
        f"/api/v1/forecasts/{prod.id}?warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["product_id"] == prod.id

    # 3. Get Actual vs Predicted timeline
    avp_resp = await async_client.get(
        f"/api/v1/forecasts/{prod.id}/actual-vs-predicted?warehouse_id={wh.id}&history_days=15",
        headers=auth_headers
    )
    assert avp_resp.status_code == 200
    avp_data = avp_resp.json()
    assert len(avp_data["points"]) > 30
    assert any(p["predicted_demand"] is not None for p in avp_data["points"])
