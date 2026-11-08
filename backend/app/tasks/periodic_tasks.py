import asyncio
import concurrent.futures
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.logging import logger
from backend.app.models.product import Product
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.reorder_policy import ReorderPolicy
from backend.app.services.anomaly_service import AnomalyDetectionService
from backend.app.services.forecast_service import ForecastService
from backend.app.services.replenishment_service import ReplenishmentService
from backend.app.services.supplier_gateway import SupplierGatewayService
from backend.app.tasks.celery_app import celery_app


def _run_async(coro):
    """Safely runs async coroutine whether called from sync Celery worker or active event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


@celery_app.task(name="backend.app.tasks.periodic_tasks.evaluate_reorder_points")
def evaluate_reorder_points() -> Dict[str, Any]:
    """
    Hourly Periodic Task:
    1. Evaluates all active reorder policies.
    2. Calculates effective stock vs ROP.
    3. Autonomously generates POs for triggered items.
    4. Auto-approves or marks NEEDS_REVIEW based on policy thresholds.
    5. Dispatches auto-approved POs to suppliers via Gateway.
    """
    async def _runner():
        async with AsyncSessionLocal() as db:
            logger.info("Executing periodic evaluate_reorder_points sweep...")
            report = await ReplenishmentService.evaluate_all_replenishment(db=db)

            # Auto-dispatch any newly created AUTO_APPROVED POs
            dispatched = []
            stmt = select(PurchaseOrder).where(
                PurchaseOrder.status == "AUTO_APPROVED"
            )
            res = await db.execute(stmt)
            auto_approved_pos = res.scalars().all()

            for po in auto_approved_pos:
                try:
                    disp = await SupplierGatewayService.dispatch_purchase_order(db=db, po_id=po.id)
                    dispatched.append(disp.po_number)
                except Exception as e:
                    logger.error(f"Failed to auto-dispatch PO {po.po_number}: {e}")

            logger.info(
                f"ROP Sweep complete: Evaluated {report.evaluated_skus}, "
                f"Triggered {report.triggered_skus}, POs Generated {report.purchase_orders_created}, "
                f"Dispatched {len(dispatched)}"
            )

            return {
                "evaluated_skus": report.evaluated_skus,
                "triggered_skus": report.triggered_skus,
                "purchase_orders_created": report.purchase_orders_created,
                "total_spend_committed": float(report.total_spend_committed),
                "dispatched_pos": dispatched,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

    return _run_async(_runner())


@celery_app.task(name="backend.app.tasks.periodic_tasks.refresh_demand_forecasts")
def refresh_demand_forecasts() -> Dict[str, Any]:
    """
    Daily Periodic Task (02:00 UTC):
    1. Refreshes 7-day and 30-day ML demand forecasts for all active SKUs.
    2. Updates dynamic safety stock and ROP in reorder policies.
    """
    async def _runner():
        async with AsyncSessionLocal() as db:
            logger.info("Executing periodic refresh_demand_forecasts...")
            stmt_prods = select(Product)
            p_res = await db.execute(stmt_prods)
            products = p_res.scalars().all()

            generated_count = 0
            for prod in products:
                for horizon in [7, 30]:
                    try:
                        await ForecastService.generate_forecast(
                            db=db,
                            product_id=prod.id,
                            horizon_days=horizon,
                            use_prophet=False
                        )
                        generated_count += 1
                    except Exception as e:
                        logger.warning(f"Could not generate {horizon}d forecast for SKU {prod.sku}: {e}")

                # Update reorder policy with refreshed daily demand & sigma
                try:
                    stmt_pol = select(ReorderPolicy).where(ReorderPolicy.product_id == prod.id)
                    res_pol = await db.execute(stmt_pol)
                    policies = res_pol.scalars().all()
                    for pol in policies:
                        await ReplenishmentService.compute_and_update_targets(db=db, policy=pol, product=prod)
                except Exception as e:
                    logger.warning(f"Could not recalculate policy for SKU {prod.sku}: {e}")

            logger.info(f"Forecast refresh complete: Generated {generated_count} forecasts for {len(products)} products.")
            return {
                "products_scanned": len(products),
                "forecasts_generated": generated_count,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

    return _run_async(_runner())


@celery_app.task(name="backend.app.tasks.periodic_tasks.followup_delayed_pos")
def followup_delayed_pos() -> Dict[str, Any]:
    """
    6-Hourly Periodic Task:
    Scans for purchase orders pending confirmation > 48h or overdue past confirmed ETA.
    Generates supplier follow-ups and logs system exception alerts.
    """
    async def _runner():
        async with AsyncSessionLocal() as db:
            logger.info("Executing periodic followup_delayed_pos...")
            followups = await SupplierGatewayService.scan_and_followup_overdue_pos(db)
            logger.info(f"Delayed PO scan complete: Logged {len(followups)} follow-ups.")
            return {
                "followups_logged": len(followups),
                "details": followups,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

    return _run_async(_runner())


@celery_app.task(name="backend.app.tasks.periodic_tasks.audit_inventory_drift")
def audit_inventory_drift() -> Dict[str, Any]:
    """
    Daily Periodic Task (04:00 UTC):
    Verifies that cached stock levels match the integral sum of ledger transactions.
    Fires CRITICAL alerts on any detected drift.
    """
    async def _runner():
        async with AsyncSessionLocal() as db:
            logger.info("Executing periodic audit_inventory_drift...")
            anomalies = await AnomalyDetectionService.audit_stock_drift(db)
            await db.commit()
            logger.info(f"Drift audit complete: {len(anomalies)} drift discrepancies found.")
            return {
                "drift_anomalies_count": len(anomalies),
                "details": [a.model_dump() for a in anomalies],
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

    return _run_async(_runner())


@celery_app.task(name="backend.app.tasks.periodic_tasks.detect_dead_stock")
def detect_dead_stock(threshold_days: int = 60) -> Dict[str, Any]:
    """
    Weekly Periodic Task:
    Flags SKUs with positive on-hand inventory but zero sales in the last 60+ days.
    """
    async def _runner():
        async with AsyncSessionLocal() as db:
            logger.info(f"Executing periodic detect_dead_stock (threshold: {threshold_days} days)...")
            anomalies = await AnomalyDetectionService.detect_dead_stock(db, threshold_days=threshold_days)
            await db.commit()
            logger.info(f"Dead stock audit complete: {len(anomalies)} dead stock items flagged.")
            return {
                "dead_stock_count": len(anomalies),
                "details": [a.model_dump() for a in anomalies],
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

    return _run_async(_runner())


@celery_app.task(name="backend.app.tasks.periodic_tasks.run_full_anomaly_sweep")
def run_full_anomaly_sweep() -> Dict[str, Any]:
    """
    Daily Periodic Task (05:00 UTC):
    Executes full anomaly audit sweep across all exception vectors.
    """
    async def _runner():
        async with AsyncSessionLocal() as db:
            logger.info("Executing periodic run_full_anomaly_sweep...")
            res = await AnomalyDetectionService.run_full_anomaly_audit(db)
            logger.info(f"Full anomaly sweep complete: {res.total_anomalies_detected} anomalies detected.")
            return {
                "total_anomalies": res.total_anomalies_detected,
                "stock_drift": res.stock_drift_count,
                "demand_spikes": res.demand_spike_count,
                "dead_stock": res.dead_stock_count,
                "supplier_delays": res.supplier_delay_count,
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

    return _run_async(_runner())
