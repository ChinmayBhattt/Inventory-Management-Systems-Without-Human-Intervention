from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import numpy as np
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.alert import Alert
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.product import Product
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.stock_level import StockLevel
from backend.app.models.warehouse import Warehouse
from backend.app.schemas.alert import AnomalyAuditItem, AnomalyAuditResponse


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class AnomalyDetectionService:
    @staticmethod
    async def create_alert_if_not_open(
        db: AsyncSession,
        alert_type: str,
        severity: str,
        message: str,
        product_id: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Alert]:
        """Insert alert only if an identical open alert does not already exist."""
        stmt = select(Alert).where(
            Alert.alert_type == alert_type,
            Alert.status == "OPEN"
        )
        if product_id:
            stmt = stmt.where(Alert.product_id == product_id)
        if warehouse_id:
            stmt = stmt.where(Alert.warehouse_id == warehouse_id)

        res = await db.execute(stmt)
        existing_alerts = res.scalars().all()
        po_target = context_data.get("po_number") if context_data else None
        for ex in existing_alerts:
            if po_target:
                if ex.context_data and ex.context_data.get("po_number") == po_target:
                    return None
            elif ex.message == message or (product_id and ex.product_id == product_id):
                return None

        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            product_id=product_id,
            warehouse_id=warehouse_id,
            message=message,
            context_data=context_data,
            status="OPEN"
        )
        db.add(alert)
        await db.flush()
        logger.warning(f"Anomaly detected: [{severity}] {alert_type}: {message}")

        if settings.SLACK_WEBHOOK_URL:
            try:
                emoji = "🚨" if severity == "CRITICAL" else "⚠️"
                payload = {
                    "text": f"{emoji} *AutoStock Alert [{severity}]*: `{alert_type}`\n>{message}"
                }
                async with httpx.AsyncClient(timeout=2.0) as client:
                    await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
            except Exception as e:
                logger.debug(f"Slack webhook dispatch skipped: {e}")

        return alert

    @staticmethod
    async def audit_stock_drift(db: AsyncSession) -> List[AnomalyAuditItem]:
        """
        Stock Drift Audit:
        Compares cached stock_levels.on_hand against the integral sum of immutable transactions.
        Integrity invariant: discrepancy == 0.
        """
        stmt = select(StockLevel).options(selectinload(StockLevel.product))
        res = await db.execute(stmt)
        stock_levels = res.scalars().all()

        anomalies = []
        for stock in stock_levels:
            stmt_sum = select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0)).where(
                InventoryTransaction.product_id == stock.product_id,
                InventoryTransaction.warehouse_id == stock.warehouse_id
            )
            res_sum = await db.execute(stmt_sum)
            ledger_sum = int(res_sum.scalar() or 0)

            discrepancy = stock.on_hand - ledger_sum
            if discrepancy != 0:
                sku = stock.product.sku if stock.product else stock.product_id
                msg = f"Stock drift detected on SKU {sku}: Cached {stock.on_hand} vs Ledger {ledger_sum} (Diff: {discrepancy})"
                await AnomalyDetectionService.create_alert_if_not_open(
                    db=db,
                    alert_type="STOCK_DRIFT",
                    severity="CRITICAL",
                    message=msg,
                    product_id=stock.product_id,
                    warehouse_id=stock.warehouse_id,
                    context_data={"cached_on_hand": stock.on_hand, "ledger_sum": ledger_sum, "drift": discrepancy}
                )
                anomalies.append(
                    AnomalyAuditItem(
                        category="STOCK_DRIFT",
                        severity="CRITICAL",
                        entity_id=stock.product_id,
                        detail=msg
                    )
                )
        return anomalies

    @staticmethod
    async def detect_demand_spikes(db: AsyncSession) -> List[AnomalyAuditItem]:
        """
        Demand Spike Audit:
        Flags products where today's sales exceed 3 standard deviations above 30-day baseline (Z-score > 3.0).
        """
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        p_res = await db.execute(select(Product))
        products = p_res.scalars().all()

        anomalies = []
        for prod in products:
            stmt_hist = select(InventoryTransaction.created_at, InventoryTransaction.quantity_delta).where(
                InventoryTransaction.product_id == prod.id,
                InventoryTransaction.transaction_type == "SALE",
                InventoryTransaction.created_at >= thirty_days_ago,
                InventoryTransaction.created_at < today_start
            )
            res_hist = await db.execute(stmt_hist)
            rows = res_hist.all()

            if len(rows) < 5:
                continue

            # Aggregate historical daily sales totals
            daily_sales: Dict[str, int] = {}
            for dt, delta in rows:
                day_key = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                daily_sales[day_key] = daily_sales.get(day_key, 0) + abs(int(delta))

            hist_values = list(daily_sales.values())
            if len(hist_values) < 5:
                continue

            mean = float(np.mean(hist_values))
            raw_std = float(np.std(hist_values))
            std = max(raw_std, 0.1 * mean, 0.5)

            # Today's sales
            stmt_today = select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0)).where(
                InventoryTransaction.product_id == prod.id,
                InventoryTransaction.transaction_type == "SALE",
                InventoryTransaction.created_at >= today_start
            )
            res_today = await db.execute(stmt_today)
            today_qty = abs(int(res_today.scalar() or 0))

            if today_qty > 0:
                z_score = (today_qty - mean) / std
                if z_score > 3.0:
                    msg = f"Demand spike on SKU {prod.sku}: Today's sales {today_qty} is {z_score:.1f}σ above baseline (mean: {mean:.1f})."
                    await AnomalyDetectionService.create_alert_if_not_open(
                        db=db,
                        alert_type="DEMAND_SPIKE",
                        severity="WARNING",
                        message=msg,
                        product_id=prod.id,
                        context_data={"today_sales": today_qty, "mean": mean, "z_score": round(z_score, 2)}
                    )
                    anomalies.append(
                        AnomalyAuditItem(
                            category="DEMAND_SPIKE",
                            severity="WARNING",
                            entity_id=prod.id,
                            detail=msg
                        )
                    )
        return anomalies

    @staticmethod
    async def detect_dead_stock(db: AsyncSession, threshold_days: int = 60) -> List[AnomalyAuditItem]:
        """
        Dead Stock Audit:
        Flags products with positive on_hand physical inventory but zero SALE events in the last 60+ days.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=threshold_days)
        stmt_stocks = select(StockLevel).options(selectinload(StockLevel.product)).where(StockLevel.on_hand > 0)
        res_stocks = await db.execute(stmt_stocks)
        stocks = res_stocks.scalars().all()

        anomalies = []
        for stock in stocks:
            stock_created = _ensure_utc(stock.created_at)
            if stock_created and stock_created >= cutoff_date:
                continue

            stmt_recent_sale = select(InventoryTransaction.id).where(
                InventoryTransaction.product_id == stock.product_id,
                InventoryTransaction.warehouse_id == stock.warehouse_id,
                InventoryTransaction.transaction_type == "SALE",
                InventoryTransaction.created_at >= cutoff_date
            ).limit(1)
            res_sale = await db.execute(stmt_recent_sale)
            has_sales = res_sale.scalar_one_or_none() is not None

            if not has_sales:
                prod = stock.product
                tied_capital = float(stock.on_hand * (prod.unit_cost if prod else 0))
                sku = prod.sku if prod else stock.product_id
                msg = f"Dead stock detected for SKU {sku}: {stock.on_hand} units unsold for > {threshold_days} days. Tied capital: ${tied_capital:.2f}."
                await AnomalyDetectionService.create_alert_if_not_open(
                    db=db,
                    alert_type="DEAD_STOCK",
                    severity="WARNING",
                    message=msg,
                    product_id=stock.product_id,
                    warehouse_id=stock.warehouse_id,
                    context_data={"on_hand": stock.on_hand, "tied_capital": tied_capital, "days_inactive": threshold_days}
                )
                anomalies.append(
                    AnomalyAuditItem(
                        category="DEAD_STOCK",
                        severity="WARNING",
                        entity_id=stock.product_id,
                        detail=msg
                    )
                )
        return anomalies

    @staticmethod
    async def detect_negative_stock(db: AsyncSession) -> List[AnomalyAuditItem]:
        """Flag any stock levels where available or physical on_hand is negative."""
        stmt = select(StockLevel).options(selectinload(StockLevel.product)).where(
            (StockLevel.on_hand < 0) | (StockLevel.available < 0)
        )
        res = await db.execute(stmt)
        negs = res.scalars().all()

        anomalies = []
        for stock in negs:
            sku = stock.product.sku if stock.product else stock.product_id
            msg = f"CRITICAL: Negative inventory balance on SKU {sku}: on_hand={stock.on_hand}, available={stock.available}."
            await AnomalyDetectionService.create_alert_if_not_open(
                db=db,
                alert_type="NEGATIVE_STOCK",
                severity="CRITICAL",
                message=msg,
                product_id=stock.product_id,
                warehouse_id=stock.warehouse_id,
                context_data={"on_hand": stock.on_hand, "available": stock.available}
            )
            anomalies.append(
                AnomalyAuditItem(category="NEGATIVE_STOCK", severity="CRITICAL", entity_id=stock.product_id, detail=msg)
            )
        return anomalies

    @staticmethod
    async def detect_supplier_delays(db: AsyncSession) -> List[AnomalyAuditItem]:
        """Flag open purchase orders that have exceeded their expected delivery date."""
        now = datetime.now(timezone.utc)
        stmt = select(PurchaseOrder).where(
            PurchaseOrder.status.in_(["AUTO_APPROVED", "SENT", "CONFIRMED"]),
            PurchaseOrder.expected_delivery_date < now
        )
        res = await db.execute(stmt)
        delayed_pos = res.scalars().all()

        anomalies = []
        for po in delayed_pos:
            days = (now - _ensure_utc(po.expected_delivery_date)).days if po.expected_delivery_date else 0
            msg = f"Purchase Order {po.po_number} is delayed by {days} days past ETA ({po.expected_delivery_date.strftime('%Y-%m-%d')})."
            await AnomalyDetectionService.create_alert_if_not_open(
                db=db,
                alert_type="SUPPLIER_DELAY",
                severity="CRITICAL",
                message=msg,
                warehouse_id=po.warehouse_id,
                context_data={"po_number": po.po_number, "days_delayed": days}
            )
            anomalies.append(
                AnomalyAuditItem(category="SUPPLIER_DELAY", severity="CRITICAL", entity_id=po.id, detail=msg)
            )
        return anomalies

    @staticmethod
    async def run_full_anomaly_audit(db: AsyncSession) -> AnomalyAuditResponse:
        """Run complete anomaly audit sweep across all exception vectors."""
        drift_items = await AnomalyDetectionService.audit_stock_drift(db)
        spike_items = await AnomalyDetectionService.detect_demand_spikes(db)
        dead_items = await AnomalyDetectionService.detect_dead_stock(db)
        neg_items = await AnomalyDetectionService.detect_negative_stock(db)
        delay_items = await AnomalyDetectionService.detect_supplier_delays(db)

        all_anomalies = drift_items + spike_items + dead_items + neg_items + delay_items
        await db.commit()

        return AnomalyAuditResponse(
            total_anomalies_detected=len(all_anomalies),
            stock_drift_count=len(drift_items),
            demand_spike_count=len(spike_items),
            dead_stock_count=len(dead_items),
            supplier_delay_count=len(delay_items),
            audited_at=datetime.now(timezone.utc),
            anomalies=all_anomalies
        )
