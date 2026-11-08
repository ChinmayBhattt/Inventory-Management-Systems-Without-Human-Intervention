import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import os
import pytest
from sqlalchemy import func, select

from backend.app.models.alert import Alert
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.product import Product
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.reorder_policy import ReorderPolicy
from backend.app.models.stock_level import StockLevel
from backend.app.models.supplier import Supplier
from backend.app.models.user import User
from backend.app.models.warehouse import Warehouse
from backend.app.tasks.celery_app import celery_app
from backend.app.tasks.periodic_tasks import (
    audit_inventory_drift,
    detect_dead_stock,
    evaluate_reorder_points,
    followup_delayed_pos,
    refresh_demand_forecasts,
    run_full_anomaly_sweep,
)
from scripts.seed_data import generate_daily_sales_series, seed_database


def test_celery_configuration_and_schedule():
    """Verify Celery app configuration, serializers, and Beat schedule."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.enable_utc is True

    schedule = celery_app.conf.beat_schedule
    expected_tasks = {
        "evaluate-reorder-points-hourly",
        "refresh-demand-forecasts-daily",
        "followup-delayed-pos-6hourly",
        "audit-inventory-drift-daily",
        "detect-dead-stock-weekly",
        "run-full-anomaly-sweep-daily",
    }
    assert expected_tasks.issubset(set(schedule.keys()))

    # Verify task names
    assert schedule["evaluate-reorder-points-hourly"]["task"] == "backend.app.tasks.periodic_tasks.evaluate_reorder_points"
    assert schedule["refresh-demand-forecasts-daily"]["task"] == "backend.app.tasks.periodic_tasks.refresh_demand_forecasts"
    assert schedule["followup-delayed-pos-6hourly"]["task"] == "backend.app.tasks.periodic_tasks.followup_delayed_pos"
    assert schedule["audit-inventory-drift-daily"]["task"] == "backend.app.tasks.periodic_tasks.audit_inventory_drift"
    assert schedule["detect-dead-stock-weekly"]["task"] == "backend.app.tasks.periodic_tasks.detect_dead_stock"
    assert schedule["run-full-anomaly-sweep-daily"]["task"] == "backend.app.tasks.periodic_tasks.run_full_anomaly_sweep"


def test_seed_sales_generator_math():
    """Verify mathematical properties of 12-month synthetic sales generation."""
    series = generate_daily_sales_series(base_daily_demand=10.0, days=365)
    assert len(series) == 365
    assert all(isinstance(x, int) and x >= 0 for x in series)

    # Check weekend seasonality
    # In generate_daily_sales_series, t % 7 == 5 is Saturday, 6 is Sunday
    saturdays = [series[t] for t in range(365) if t % 7 == 5]
    mondays = [series[t] for t in range(365) if t % 7 == 0]
    assert sum(saturdays) / len(saturdays) > sum(mondays) / len(mondays)

    # Check Black Friday spike (days 320 to 328)
    bf_sales = series[320:328]
    baseline_sales = series[20:100]
    assert (sum(bf_sales) / len(bf_sales)) > (sum(baseline_sales) / len(baseline_sales) * 2.0)


@pytest.mark.asyncio
async def test_periodic_tasks_direct_invocation():
    """Verify all Celery periodic tasks execute directly in synchronous eager mode."""
    celery_app.conf.task_always_eager = True

    # 1. Audit drift
    drift_res = audit_inventory_drift()
    assert "drift_anomalies_count" in drift_res
    assert "executed_at" in drift_res

    # 2. Delayed POs followup
    follow_res = followup_delayed_pos()
    assert "followups_logged" in follow_res

    # 3. Dead stock
    dead_res = detect_dead_stock(threshold_days=60)
    assert "dead_stock_count" in dead_res

    # 4. Full anomaly sweep
    sweep_res = run_full_anomaly_sweep()
    assert "total_anomalies" in sweep_res

    # 5. Evaluate reorder points
    rop_res = evaluate_reorder_points()
    assert "evaluated_skus" in rop_res


@pytest.mark.asyncio
async def test_seed_database_end_to_end_integrity():
    """
    Execute seed_database and verify:
    - 50 SKUs across categories
    - 3 Warehouses, 5 Suppliers, 2 Users
    - 50 Reorder Policies
    - > 15,000 immutable transactions
    - Stock drift = 0 across all stock levels
    """
    await seed_database(clear_existing=True)

    from backend.app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # 1. Users
        users_count = (await session.execute(select(func.count(User.id)))).scalar()
        assert users_count == 2

        # 2. Warehouses
        wh_count = (await session.execute(select(func.count(Warehouse.id)))).scalar()
        assert wh_count == 3

        # 3. Suppliers
        supp_count = (await session.execute(select(func.count(Supplier.id)))).scalar()
        assert supp_count == 5

        # 4. Products (50 SKUs)
        prod_count = (await session.execute(select(func.count(Product.id)))).scalar()
        assert prod_count == 50

        # Check category distribution
        elec_count = (await session.execute(select(func.count(Product.id)).where(Product.category == "Electronics"))).scalar()
        app_count = (await session.execute(select(func.count(Product.id)).where(Product.category == "Apparel"))).scalar()
        groc_count = (await session.execute(select(func.count(Product.id)).where(Product.category == "Groceries"))).scalar()
        assert elec_count == 18
        assert app_count == 16
        assert groc_count == 16

        # 5. Reorder Policies
        policy_count = (await session.execute(select(func.count(ReorderPolicy.id)))).scalar()
        assert policy_count == 50

        # 6. Transactions (> 15,000)
        tx_count = (await session.execute(select(func.count(InventoryTransaction.id)))).scalar()
        assert tx_count > 15000

        # 7. Zero Stock Drift Invariant Verification
        stock_res = await session.execute(select(StockLevel))
        stocks = stock_res.scalars().all()
        assert len(stocks) == 50

        for stock in stocks:
            tx_sum_res = await session.execute(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0)).where(
                    InventoryTransaction.product_id == stock.product_id,
                    InventoryTransaction.warehouse_id == stock.warehouse_id
                )
            )
            ledger_sum = int(tx_sum_res.scalar() or 0)
            # Drift must be exactly zero
            assert stock.on_hand == ledger_sum, f"Stock drift detected on product {stock.product_id}: {stock.on_hand} vs {ledger_sum}"
            assert stock.available == stock.on_hand - stock.reserved
            assert stock.on_hand >= 0

