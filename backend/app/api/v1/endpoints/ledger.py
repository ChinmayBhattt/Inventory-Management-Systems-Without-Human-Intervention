from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.stock_level import StockLevel
from backend.app.models.user import User
from backend.app.schemas.ledger import (
    AdjustmentRequest,
    ReconciliationResponse,
    StockLevelResponse,
    TransactionResponse,
)
from backend.app.services.ledger_service import InventoryLedgerService

router = APIRouter()


@router.get("/stock-levels", response_model=List[StockLevelResponse])
async def get_stock_levels(
    product_id: Optional[str] = Query(None, description="Filter by Product UUID"),
    warehouse_id: Optional[str] = Query(None, description="Filter by Warehouse UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve current materialized stock levels across warehouses."""
    stmt = select(StockLevel)
    if product_id:
        stmt = stmt.where(StockLevel.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)

    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    product_id: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve immutable event-sourced inventory transaction audit trail."""
    stmt = select(InventoryTransaction).order_by(desc(InventoryTransaction.created_at))
    if product_id:
        stmt = stmt.where(InventoryTransaction.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(InventoryTransaction.warehouse_id == warehouse_id)
    if transaction_type:
        stmt = stmt.where(InventoryTransaction.transaction_type == transaction_type)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/adjustment", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def record_adjustment(
    adj_in: AdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    Admin-only endpoint: record manual inventory adjustment, cycle count correction, damage write-off, or return.
    """
    tx, _ = await InventoryLedgerService.record_transaction(
        db=db,
        product_id=adj_in.product_id,
        warehouse_id=adj_in.warehouse_id,
        transaction_type=adj_in.adjustment_type,
        quantity_delta=adj_in.quantity_delta,
        reference_type="MANUAL_ADJUSTMENT",
        reference_id=admin_user.id,
        idempotency_key=adj_in.idempotency_key,
        metadata_json={
            "adjusted_by": admin_user.email,
            "reason": adj_in.reason
        }
    )
    await db.commit()
    await db.refresh(tx)
    return tx


@router.post("/reconcile", response_model=ReconciliationResponse)
async def reconcile_inventory(
    product_id: str,
    warehouse_id: str,
    auto_correct: bool = Query(False, description="Whether to overwrite stock_levels with ledger integral"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    Reconcile cached stock_level with the integral sum of all immutable transactions.
    """
    result = await InventoryLedgerService.reconcile_stock_levels(
        db=db,
        product_id=product_id,
        warehouse_id=warehouse_id,
        auto_correct=auto_correct
    )
    if auto_correct:
        await db.commit()
    return result

