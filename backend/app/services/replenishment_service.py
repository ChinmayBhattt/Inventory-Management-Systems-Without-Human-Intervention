from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.logging import logger
from backend.app.core.redis import redis_manager
from backend.app.models.alert import Alert
from backend.app.models.forecast import Forecast
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.product import Product
from backend.app.models.purchase_order import POItem, PurchaseOrder
from backend.app.models.reorder_policy import ReorderPolicy
from backend.app.models.stock_level import StockLevel
from backend.app.models.supplier import Supplier
from backend.app.models.warehouse import Warehouse
from backend.app.schemas.replenishment import (
    ReorderPolicyCreate,
    ReorderPolicyUpdate,
    ReplenishmentEvaluationItem,
    ReplenishmentRunResponse,
)
from backend.app.services.ledger_service import InventoryLedgerService
from backend.app.services.po_pdf_generator import PurchaseOrderPDFGenerator
from backend.app.services.replenishment_math import (
    calculate_economic_order_quantity,
    calculate_reorder_point,
    calculate_safety_stock,
    evaluate_replenishment_trigger,
)


class ReplenishmentService:
    @staticmethod
    async def get_or_create_policy(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str
    ) -> ReorderPolicy:
        """Fetch existing reorder policy or initialize default policy."""
        stmt = select(ReorderPolicy).where(
            ReorderPolicy.product_id == product_id,
            ReorderPolicy.warehouse_id == warehouse_id
        )
        res = await db.execute(stmt)
        policy = res.scalar_one_or_none()
        if not policy:
            policy = ReorderPolicy(
                product_id=product_id,
                warehouse_id=warehouse_id,
                service_level_z=1.65,
                lead_time_days=7,
                holding_cost_annual_pct=0.20,
                fixed_order_cost=Decimal("50.00"),
                safety_stock=10,
                reorder_point=25,
                economic_order_quantity=50,
                auto_approve_max_po_value=Decimal("5000.00"),
                is_autonomous=True,
            )
            db.add(policy)
            await db.flush()
        return policy

    @staticmethod
    async def compute_and_update_targets(
        db: AsyncSession,
        policy: ReorderPolicy,
        product: Product
    ) -> ReorderPolicy:
        """
        Dynamically calculate Safety Stock, ROP, and EOQ based on empirical sales demand:
        - Daily demand mean and std deviation over last 60 days
        - Lead time and holding cost formulas
        """
        sixty_days_ago = datetime.now(timezone.utc) - timedelta(days=60)
        stmt_sales = select(InventoryTransaction.quantity_delta).where(
            InventoryTransaction.product_id == policy.product_id,
            InventoryTransaction.warehouse_id == policy.warehouse_id,
            InventoryTransaction.transaction_type == "SALE",
            InventoryTransaction.created_at >= sixty_days_ago
        )
        res_sales = await db.execute(stmt_sales)
        sales = [abs(q) for q in res_sales.scalars().all()]

        if len(sales) >= 5:
            avg_daily = float(np.mean(sales))
            sigma_daily = float(np.std(sales))
        else:
            # Fallback to forecast if available
            f_stmt = select(func.avg(Forecast.predicted_demand)).where(
                Forecast.product_id == policy.product_id,
                Forecast.warehouse_id == policy.warehouse_id
            )
            f_res = await db.execute(f_stmt)
            f_avg = f_res.scalar()
            avg_daily = float(f_avg) if f_avg is not None else 5.0
            sigma_daily = max(1.0, avg_daily * 0.3)

        annual_demand = avg_daily * 365.0
        unit_cost = float(product.unit_cost)

        # 1. Safety Stock
        ss = calculate_safety_stock(
            service_level_z=policy.service_level_z,
            sigma_demand=sigma_daily,
            lead_time_days=policy.lead_time_days
        )

        # 2. Reorder Point
        rop = calculate_reorder_point(
            avg_daily_demand=avg_daily,
            lead_time_days=policy.lead_time_days,
            safety_stock=ss
        )

        # 3. Economic Order Quantity
        eoq = calculate_economic_order_quantity(
            annual_demand=annual_demand,
            fixed_order_cost=float(policy.fixed_order_cost),
            unit_cost=unit_cost,
            holding_cost_annual_pct=policy.holding_cost_annual_pct
        )

        policy.safety_stock = ss
        policy.reorder_point = rop
        policy.economic_order_quantity = eoq
        await db.flush()
        return policy

    @staticmethod
    async def evaluate_product_replenishment(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str
    ) -> ReplenishmentEvaluationItem:
        """
        Evaluate single product replenishment trigger and generate PO if needed.
        """
        # Fetch Product & Warehouse
        p_res = await db.execute(select(Product).options(selectinload(Product.default_supplier)).where(Product.id == product_id))
        product = p_res.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

        w_res = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
        warehouse = w_res.scalar_one_or_none()
        if not warehouse:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

        # Lock and read stock level
        stock = await InventoryLedgerService.get_or_create_stock_level(db, product_id, warehouse_id, for_update=True)
        policy = await ReplenishmentService.get_or_create_policy(db, product_id, warehouse_id)

        # Refresh mathematical targets
        policy = await ReplenishmentService.compute_and_update_targets(db, policy, product)

        # Supplier lookup
        supplier = product.default_supplier
        if not supplier:
            s_res = await db.execute(select(Supplier).limit(1))
            supplier = s_res.scalar_one_or_none()

        supplier_lead = supplier.lead_time_days if supplier else policy.lead_time_days
        supplier_rel = supplier.reliability_score if supplier else 1.0

        # Evaluate Trigger
        is_triggered, effective_stock, recommended_qty = evaluate_replenishment_trigger(
            on_hand=stock.on_hand,
            on_order=stock.on_order,
            reserved=stock.reserved,
            reorder_point=policy.reorder_point,
            economic_order_quantity=policy.economic_order_quantity,
            moq=1
        )

        if not is_triggered or recommended_qty <= 0:
            return ReplenishmentEvaluationItem(
                product_id=product_id,
                sku=product.sku,
                warehouse_id=warehouse_id,
                on_hand=stock.on_hand,
                on_order=stock.on_order,
                reserved=stock.reserved,
                effective_stock=effective_stock,
                reorder_point=policy.reorder_point,
                economic_order_quantity=policy.economic_order_quantity,
                is_triggered=False,
                recommended_order_quantity=0,
                po_generated=False,
                estimated_cost=Decimal("0.00")
            )

        # Replenishment Triggered -> Generate Purchase Order
        po_number = f"PO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        total_cost = Decimal(str(recommended_qty)) * product.unit_cost

        # Auto-Approval Rule Evaluation
        # 1. Product autonomy enabled
        # 2. Total cost within auto-approval ceiling
        # 3. Supplier reliability >= 0.80
        is_auto_approved = (
            policy.is_autonomous
            and total_cost <= policy.auto_approve_max_po_value
            and supplier_rel >= 0.80
        )

        po_status = "AUTO_APPROVED" if is_auto_approved else "NEEDS_REVIEW"
        approval_mode = "AUTONOMOUS" if is_auto_approved else "MANUAL"

        expected_delivery = datetime.now(timezone.utc) + timedelta(days=supplier_lead)

        po = PurchaseOrder(
            po_number=po_number,
            supplier_id=supplier.id if supplier else None,
            warehouse_id=warehouse_id,
            status=po_status,
            approval_mode=approval_mode,
            total_cost=total_cost,
            expected_delivery_date=expected_delivery,
            notes=f"Generated autonomously: Effective stock {effective_stock} <= ROP {policy.reorder_point}."
        )
        db.add(po)
        await db.flush()

        po_item = POItem(
            po_id=po.id,
            product_id=product.id,
            quantity_ordered=recommended_qty,
            quantity_received=0,
            unit_cost=product.unit_cost
        )
        db.add(po_item)

        # If auto-approved, immediately credit on_order counter
        if is_auto_approved:
            stock.on_order += recommended_qty
            await db.flush()
        else:
            # Create exception alert for human review
            alert = Alert(
                alert_type="PO_NEEDS_REVIEW",
                severity="WARNING",
                product_id=product.id,
                warehouse_id=warehouse_id,
                message=(
                    f"PO {po_number} for {recommended_qty} units of {product.sku} requires human review. "
                    f"Value: ${total_cost:.2f} (Limit: ${policy.auto_approve_max_po_value:.2f}), "
                    f"Supplier Score: {supplier_rel:.2f}"
                ),
                context_data={
                    "po_number": po_number,
                    "po_id": po.id,
                    "total_cost": float(total_cost),
                    "policy_limit": float(policy.auto_approve_max_po_value),
                    "supplier_score": supplier_rel
                },
                status="OPEN"
            )
            db.add(alert)

        # Generate PDF document
        items_for_pdf = [{
            "sku": product.sku,
            "name": product.name,
            "quantity_ordered": recommended_qty,
            "unit_cost": float(product.unit_cost)
        }]
        pdf_path = PurchaseOrderPDFGenerator.generate_pdf(
            po_number=po_number,
            supplier_name=supplier.name if supplier else "General Supplier",
            supplier_email=supplier.email if supplier else "supplier@example.com",
            warehouse_name=warehouse.name,
            warehouse_code=warehouse.code,
            created_at=po.created_at,
            expected_delivery=expected_delivery,
            items=items_for_pdf,
            total_cost=total_cost,
            status=po_status,
            approval_mode=approval_mode
        )
        po.pdf_storage_path = pdf_path

        await db.commit()

        logger.info(
            f"Replenishment executed for {product.sku}: Qty {recommended_qty}, Status {po_status}, "
            f"Cost ${total_cost:.2f}"
        )

        return ReplenishmentEvaluationItem(
            product_id=product_id,
            sku=product.sku,
            warehouse_id=warehouse_id,
            on_hand=stock.on_hand,
            on_order=stock.on_order,
            reserved=stock.reserved,
            effective_stock=effective_stock,
            reorder_point=policy.reorder_point,
            economic_order_quantity=policy.economic_order_quantity,
            is_triggered=True,
            recommended_order_quantity=recommended_qty,
            po_generated=True,
            po_number=po_number,
            po_status=po_status,
            estimated_cost=total_cost
        )

    @staticmethod
    async def evaluate_all_replenishment(db: AsyncSession) -> ReplenishmentRunResponse:
        """Run replenishment sweep across all products and active warehouses."""
        products_res = await db.execute(select(Product))
        products = products_res.scalars().all()

        wh_res = await db.execute(select(Warehouse).where(Warehouse.is_active == True))
        warehouses = wh_res.scalars().all()

        evaluated = 0
        triggered = 0
        pos_created = 0
        total_spend = Decimal("0.00")
        results = []

        for wh in warehouses:
            for p in products:
                evaluated += 1
                item_res = await ReplenishmentService.evaluate_product_replenishment(
                    db=db,
                    product_id=p.id,
                    warehouse_id=wh.id
                )
                results.append(item_res)
                if item_res.is_triggered:
                    triggered += 1
                if item_res.po_generated:
                    pos_created += 1
                    total_spend += item_res.estimated_cost

        return ReplenishmentRunResponse(
            evaluated_skus=evaluated,
            triggered_skus=triggered,
            purchase_orders_created=pos_created,
            total_spend_committed=total_spend,
            items=results
        )

    @staticmethod
    async def manual_approve_po(
        db: AsyncSession,
        po_id: str,
        notes: Optional[str] = None
    ) -> PurchaseOrder:
        """Human manager approves a PO that was flagged with NEEDS_REVIEW."""
        stmt = select(PurchaseOrder).options(
            selectinload(PurchaseOrder.items),
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.warehouse)
        ).where(PurchaseOrder.id == po_id)
        res = await db.execute(stmt)
        po = res.scalar_one_or_none()
        if not po:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")

        if po.status != "NEEDS_REVIEW":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve PO in {po.status} status. Only NEEDS_REVIEW purchase orders can be approved."
            )

        # Increment on_order for all items
        for item in po.items:
            stock = await InventoryLedgerService.get_or_create_stock_level(
                db, item.product_id, po.warehouse_id, for_update=True
            )
            stock.on_order += item.quantity_ordered

        po.status = "AUTO_APPROVED"
        po.notes = (po.notes or "") + f" [Manually approved: {notes or 'No notes'}]"

        # Resolve open alerts for this PO
        alert_stmt = select(Alert).where(
            Alert.alert_type == "PO_NEEDS_REVIEW",
            Alert.status == "OPEN"
        )
        alert_res = await db.execute(alert_stmt)
        for a in alert_res.scalars().all():
            if a.context_data and a.context_data.get("po_id") == po.id:
                a.status = "RESOLVED"
                a.resolved_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(po)
        logger.info(f"Purchase Order {po.po_number} manually approved by manager.")
        return po

    @staticmethod
    async def cancel_po(db: AsyncSession, po_id: str) -> PurchaseOrder:
        """Cancel purchase order: decrements on_order if previously approved."""
        stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.id == po_id)
        res = await db.execute(stmt)
        po = res.scalar_one_or_none()
        if not po:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")

        if po.status in ["COMPLETED", "PARTIALLY_RECEIVED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel PO in {po.status} status with received goods."
            )

        # If on_order was committed, decrement it
        if po.status in ["AUTO_APPROVED", "SENT", "CONFIRMED"]:
            for item in po.items:
                stock = await InventoryLedgerService.get_or_create_stock_level(
                    db, item.product_id, po.warehouse_id, for_update=True
                )
                stock.on_order = max(0, stock.on_order - item.quantity_ordered)

        po.status = "CANCELLED"
        await db.commit()
        await db.refresh(po)
        logger.info(f"Purchase Order {po.po_number} cancelled.")
        return po

