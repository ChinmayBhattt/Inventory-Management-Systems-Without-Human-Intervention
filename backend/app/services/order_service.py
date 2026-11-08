import base64
import hashlib
import hmac
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.redis import redis_manager
from backend.app.models.order import Order, OrderItem
from backend.app.models.product import Product
from backend.app.models.warehouse import Warehouse
from backend.app.schemas.order import OrderCreate, OrderItemCreate, ShopifyWebhookPayload
from backend.app.services.ledger_service import InsufficientStockException, InventoryLedgerService


class OrderService:
    @staticmethod
    def verify_shopify_signature(raw_body: bytes, hmac_header: Optional[str]) -> bool:
        """
        Verify Shopify X-Shopify-Hmac-Sha256 header using constant-time comparison.
        Shopify calculates HMAC-SHA256 of raw request body using the shared secret and base64 encodes it.
        """
        if not hmac_header:
            return False
        
        secret = settings.SHOPIFY_WEBHOOK_SECRET.encode("utf-8")
        computed_hash = hmac.new(secret, raw_body, hashlib.sha256).digest()
        computed_hmac = base64.b64encode(computed_hash).decode("utf-8")
        
        return hmac.compare_digest(computed_hmac, hmac_header.strip())

    @staticmethod
    async def create_order(
        db: AsyncSession,
        order_in: OrderCreate,
        channel: str = "REST_API"
    ) -> Order:
        """
        Idempotently create and atomically reserve stock for an order.
        Distributed locks are held across all SKU-warehouse pairs until the transaction commits.
        """
        product_ids = sorted(list({item.product_id for item in order_in.items}))

        async with AsyncExitStack() as lock_stack:
            for pid in product_ids:
                lock_key = f"stock:{pid}:{order_in.warehouse_id}"
                await lock_stack.enter_async_context(
                    redis_manager.distributed_lock(lock_key, expire_seconds=15)
                )

            # 1. Check Idempotency
            stmt_dup = select(Order).options(selectinload(Order.items)).where(Order.idempotency_key == order_in.idempotency_key)
            res_dup = await db.execute(stmt_dup)
            existing_order = res_dup.scalar_one_or_none()
            if existing_order:
                logger.info(f"Returning existing order for idempotency key: {order_in.idempotency_key}")
                return existing_order

            # Verify warehouse exists
            stmt_wh = select(Warehouse).where(Warehouse.id == order_in.warehouse_id)
            res_wh = await db.execute(stmt_wh)
            warehouse = res_wh.scalar_one_or_none()
            if not warehouse:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Warehouse with ID {order_in.warehouse_id} not found."
                )

            # 2. Check stock and reserve atomically for all items
            reserved_items: List[dict] = []
            total_amount = Decimal("0.00")

            try:
                for item in order_in.items:
                    stmt_prod = select(Product).where(Product.id == item.product_id)
                    res_prod = await db.execute(stmt_prod)
                    product = res_prod.scalar_one_or_none()
                    if not product:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Product with ID {item.product_id} not found."
                        )

                    # Atomically reserve stock
                    item_ref = f"{order_in.order_number}:{item.product_id}"
                    item_idem = f"reserve:{order_in.idempotency_key}:{item.product_id}"
                    await InventoryLedgerService.reserve_stock(
                        db=db,
                        product_id=item.product_id,
                        warehouse_id=order_in.warehouse_id,
                        quantity=item.quantity,
                        reference_id=item_ref,
                        idempotency_key=item_idem
                    )
                    reserved_items.append({
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price
                    })
                    total_amount += item.unit_price * item.quantity

            except InsufficientStockException:
                # Roll back any already reserved items in this order
                for rev in reserved_items:
                    await InventoryLedgerService.release_reserved_stock(
                        db=db,
                        product_id=rev["product_id"],
                        warehouse_id=order_in.warehouse_id,
                        quantity=rev["quantity"],
                        reference_id=f"rollback:{order_in.order_number}"
                    )
                raise

            # 3. Create Order & Items
            order = Order(
                order_number=order_in.order_number,
                channel=channel,
                status="RESERVED",
                idempotency_key=order_in.idempotency_key,
                warehouse_id=order_in.warehouse_id,
                total_amount=total_amount
            )
            db.add(order)
            await db.flush()

            for item in reserved_items:
                oi = OrderItem(
                    order_id=order.id,
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"]
                )
                db.add(oi)

            await db.commit()

            # Reload with items
            stmt_reload = select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
            res_reload = await db.execute(stmt_reload)
            order_loaded = res_reload.scalar_one()

            logger.info(f"Order created and reserved: {order_loaded.order_number} (ID: {order_loaded.id})")
            return order_loaded

    @staticmethod
    async def fulfill_order(db: AsyncSession, order_id: str) -> Order:
        """
        Fulfill a reserved order: debits physical inventory via SALE transactions and marks FULFILLED.
        """
        stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        res = await db.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

        if order.status == "FULFILLED":
            return order
        if order.status != "RESERVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot fulfill order in {order.status} state. Must be RESERVED."
            )

        for item in order.items:
            fulfill_idem = f"fulfill:{order.id}:{item.product_id}"
            await InventoryLedgerService.fulfill_reserved_stock(
                db=db,
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                quantity=item.quantity,
                reference_id=order.order_number,
                idempotency_key=fulfill_idem
            )

        order.status = "FULFILLED"
        await db.commit()

        stmt_reload = select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
        res_reload = await db.execute(stmt_reload)
        order_loaded = res_reload.scalar_one()

        logger.info(f"Order fulfilled: {order_loaded.order_number}")
        return order_loaded

    @staticmethod
    async def cancel_order(db: AsyncSession, order_id: str) -> Order:
        """
        Cancel a reserved order: releases reserved stock back to available pool.
        """
        stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        res = await db.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

        if order.status == "CANCELLED":
            return order
        if order.status == "FULFILLED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel an already fulfilled order. Use Return workflow."
            )

        for item in order.items:
            await InventoryLedgerService.release_reserved_stock(
                db=db,
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                quantity=item.quantity,
                reference_id=f"cancel:{order.order_number}"
            )

        order.status = "CANCELLED"
        await db.commit()

        stmt_reload = select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
        res_reload = await db.execute(stmt_reload)
        order_loaded = res_reload.scalar_one()

        logger.info(f"Order cancelled and stock released: {order_loaded.order_number}")
        return order_loaded

    @staticmethod
    async def process_shopify_webhook(
        db: AsyncSession,
        raw_body: bytes,
        hmac_header: Optional[str],
        payload: Dict[str, Any],
        warehouse_id: Optional[str] = None
    ) -> Order:
        """
        Process inbound Shopify orders/create webhook:
        1. Validates HMAC signature.
        2. Resolves SKUs.
        3. Creates and reserves order.
        """
        if not OrderService.verify_shopify_signature(raw_body, hmac_header):
            logger.warning("Shopify webhook rejected: Invalid HMAC signature.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Shopify HMAC signature."
            )

        shopify_id = str(payload.get("id"))
        order_number = f"SHOPIFY-{payload.get('name', shopify_id)}"
        idempotency_key = f"shopify_webhook_{shopify_id}"

        # If warehouse_id not specified, pick default active warehouse
        if not warehouse_id:
            stmt_wh = select(Warehouse).where(Warehouse.is_active == True).limit(1)
            res_wh = await db.execute(stmt_wh)
            wh = res_wh.scalar_one_or_none()
            if not wh:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active warehouse configured for webhook ingestion."
                )
            warehouse_id = wh.id

        items_to_order = []
        for line in payload.get("line_items", []):
            sku = line.get("sku")
            quantity = int(line.get("quantity", 1))
            price = Decimal(str(line.get("price", "0.00")))

            # Find product by SKU
            stmt_p = select(Product).where(Product.sku == sku)
            res_p = await db.execute(stmt_p)
            prod = res_p.scalar_one_or_none()
            if not prod:
                logger.warning(f"Shopify webhook referenced unknown SKU: {sku}")
                continue

            items_to_order.append(
                OrderItemCreate(
                    product_id=prod.id,
                    quantity=quantity,
                    unit_price=price
                )
            )

        if not items_to_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No matching inventory products found in Shopify order payload."
            )

        order_create = OrderCreate(
            order_number=order_number,
            warehouse_id=warehouse_id,
            items=items_to_order,
            idempotency_key=idempotency_key,
            channel="SHOPIFY_WEBHOOK"
        )

        return await OrderService.create_order(db=db, order_in=order_create, channel="SHOPIFY_WEBHOOK")
