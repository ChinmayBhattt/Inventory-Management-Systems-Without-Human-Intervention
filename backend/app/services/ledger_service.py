from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.redis import redis_manager
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.stock_level import StockLevel


class InsufficientStockException(HTTPException):
    def __init__(self, detail: str = "Insufficient stock available"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class InventoryLedgerService:
    @staticmethod
    async def get_or_create_stock_level(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        for_update: bool = True
    ) -> StockLevel:
        """
        Fetch the stock_level record for a SKU at a warehouse.
        Applies SELECT ... FOR UPDATE on PostgreSQL to guarantee serialized single-writer access.
        """
        stmt = select(StockLevel).where(
            StockLevel.product_id == product_id,
            StockLevel.warehouse_id == warehouse_id
        )
        if for_update and not settings.is_sqlite:
            stmt = stmt.with_for_update()

        result = await db.execute(stmt)
        stock_level = result.scalar_one_or_none()

        if stock_level is None:
            # Initialize with zero balances
            stock_level = StockLevel(
                product_id=product_id,
                warehouse_id=warehouse_id,
                on_hand=0,
                reserved=0,
                on_order=0,
                available=0,
                last_reconciled_at=datetime.now(timezone.utc),
            )
            db.add(stock_level)
            await db.flush()
            # If PostgreSQL, re-lock the newly created row
            if for_update and not settings.is_sqlite:
                stmt_lock = select(StockLevel).where(
                    StockLevel.id == stock_level.id
                ).with_for_update()
                result_lock = await db.execute(stmt_lock)
                stock_level = result_lock.scalar_one()

        return stock_level

    @staticmethod
    async def record_transaction(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        transaction_type: str,
        quantity_delta: int,
        reference_type: str,
        reference_id: Optional[str],
        idempotency_key: str,
        metadata_json: Optional[Dict[str, Any]] = None
    ) -> Tuple[InventoryTransaction, StockLevel]:
        """
        Event-sourced write:
        1. Checks idempotency.
        2. Locks stock_levels row.
        3. Appends immutable transaction.
        4. Updates materialized stock_levels cache.
        5. Asserts invariants.
        """
        # 1. Idempotency Check
        stmt_dup = select(InventoryTransaction).where(
            InventoryTransaction.idempotency_key == idempotency_key
        )
        res_dup = await db.execute(stmt_dup)
        existing_tx = res_dup.scalar_one_or_none()
        if existing_tx:
            stock = await InventoryLedgerService.get_or_create_stock_level(
                db, product_id, warehouse_id, for_update=False
            )
            logger.info(f"Duplicate transaction skipped via idempotency key: {idempotency_key}")
            return existing_tx, stock

        lock_key = f"stock:{product_id}:{warehouse_id}"
        async with redis_manager.distributed_lock(lock_key, expire_seconds=10):
            # 2. Acquire database row-level lock
            stock = await InventoryLedgerService.get_or_create_stock_level(
                db, product_id, warehouse_id, for_update=True
            )

            # 3. Calculate new balances
            new_on_hand = stock.on_hand + quantity_delta
            new_available = new_on_hand - stock.reserved

            if new_on_hand < 0:
                raise InsufficientStockException(
                    f"Physical on-hand stock cannot be negative. Current: {stock.on_hand}, Delta: {quantity_delta}"
                )
            if new_available < 0:
                raise InsufficientStockException(
                    f"Transaction would cause negative available stock. On-hand: {new_on_hand}, Reserved: {stock.reserved}"
                )

            # 4. Append Immutable Event
            tx = InventoryTransaction(
                product_id=product_id,
                warehouse_id=warehouse_id,
                transaction_type=transaction_type,
                quantity_delta=quantity_delta,
                reference_type=reference_type,
                reference_id=reference_id,
                idempotency_key=idempotency_key,
                metadata_json=metadata_json,
                created_at=datetime.now(timezone.utc)
            )
            db.add(tx)

            # 5. Update Materialized Cache
            stock.on_hand = new_on_hand
            stock.available = new_available
            stock.last_reconciled_at = datetime.now(timezone.utc)
            await db.flush()

            logger.info(
                f"Ledger write committed: {transaction_type} {quantity_delta} for SKU {product_id}. "
                f"New on_hand: {stock.on_hand}, available: {stock.available}"
            )
            return tx, stock

    @staticmethod
    async def reserve_stock(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        quantity: int,
        reference_id: str,
        idempotency_key: str
    ) -> StockLevel:
        """
        Atomically reserve stock for an order:
        Increments reserved, decrements available.
        Does NOT alter physical on_hand until order fulfillment.
        """
        if quantity <= 0:
            raise ValueError("Reservation quantity must be strictly positive.")

        lock_key = f"stock:{product_id}:{warehouse_id}"
        async with redis_manager.distributed_lock(lock_key, expire_seconds=10):
            stock = await InventoryLedgerService.get_or_create_stock_level(
                db, product_id, warehouse_id, for_update=True
            )

            if stock.available < quantity:
                raise InsufficientStockException(
                    f"Cannot reserve {quantity} units for product {product_id}. Available: {stock.available}, On-hand: {stock.on_hand}, Reserved: {stock.reserved}"
                )

            stock.reserved += quantity
            stock.available = stock.on_hand - stock.reserved
            stock.last_reconciled_at = datetime.now(timezone.utc)
            await db.flush()

            logger.info(
                f"Reserved {quantity} units for ref {reference_id}. Product: {product_id}. "
                f"Reserved: {stock.reserved}, Available: {stock.available}"
            )
            return stock

    @staticmethod
    async def release_reserved_stock(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        quantity: int,
        reference_id: str
    ) -> StockLevel:
        """
        Release reserved stock (e.g., cancelled or expired order).
        Decrements reserved, increments available.
        """
        lock_key = f"stock:{product_id}:{warehouse_id}"
        async with redis_manager.distributed_lock(lock_key, expire_seconds=10):
            stock = await InventoryLedgerService.get_or_create_stock_level(
                db, product_id, warehouse_id, for_update=True
            )

            release_qty = min(quantity, stock.reserved)
            stock.reserved -= release_qty
            stock.available = stock.on_hand - stock.reserved
            stock.last_reconciled_at = datetime.now(timezone.utc)
            await db.flush()

            logger.info(f"Released {release_qty} reserved units for ref {reference_id}. Product: {product_id}")
            return stock

    @staticmethod
    async def fulfill_reserved_stock(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        quantity: int,
        reference_id: str,
        idempotency_key: str
    ) -> Tuple[InventoryTransaction, StockLevel]:
        """
        Fulfill reserved order:
        Releases reserved counter, applies SALE transaction debiting on_hand.
        """
        lock_key = f"stock:{product_id}:{warehouse_id}"
        async with redis_manager.distributed_lock(lock_key, expire_seconds=10):
            stock = await InventoryLedgerService.get_or_create_stock_level(
                db, product_id, warehouse_id, for_update=True
            )

            # Release reserved count
            stock.reserved = max(0, stock.reserved - quantity)

            # Record SALE transaction (-quantity)
            tx, updated_stock = await InventoryLedgerService.record_transaction(
                db=db,
                product_id=product_id,
                warehouse_id=warehouse_id,
                transaction_type="SALE",
                quantity_delta=-quantity,
                reference_type="ORDER",
                reference_id=reference_id,
                idempotency_key=idempotency_key,
                metadata_json={"fulfillment_time": datetime.now(timezone.utc).isoformat()}
            )
            return tx, updated_stock

    @staticmethod
    async def reconcile_stock_levels(
        db: AsyncSession,
        product_id: str,
        warehouse_id: str,
        auto_correct: bool = False
    ) -> Dict[str, Any]:
        """
        Reconcile materialized stock_levels.on_hand against integral of all ledger transactions.
        Integrity check: discrepancy = cached_on_hand - sum(quantity_delta).
        """
        stock = await InventoryLedgerService.get_or_create_stock_level(
            db, product_id, warehouse_id, for_update=True
        )

        stmt_sum = select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0)).where(
            InventoryTransaction.product_id == product_id,
            InventoryTransaction.warehouse_id == warehouse_id
        )
        res_sum = await db.execute(stmt_sum)
        ledger_sum = int(res_sum.scalar() or 0)

        initial_cached = stock.on_hand
        discrepancy = initial_cached - ledger_sum
        is_synchronized = (discrepancy == 0)

        if not is_synchronized and auto_correct:
            logger.warning(
                f"Correcting stock drift for SKU {product_id} at WH {warehouse_id}: "
                f"Cached {initial_cached} -> Ledger Sum {ledger_sum}"
            )
            stock.on_hand = ledger_sum
            stock.available = stock.on_hand - stock.reserved
            stock.last_reconciled_at = datetime.now(timezone.utc)
            await db.flush()

        return {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "cached_on_hand": initial_cached,
            "ledger_sum_on_hand": ledger_sum,
            "discrepancy": discrepancy,
            "is_synchronized": is_synchronized,
            "reconciled_at": datetime.now(timezone.utc)
        }
