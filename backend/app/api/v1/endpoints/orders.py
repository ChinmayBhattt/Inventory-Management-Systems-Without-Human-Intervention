import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db
from backend.app.models.order import Order, OrderItem
from backend.app.models.user import User
from backend.app.schemas.order import OrderCreate, OrderResponse
from backend.app.services.order_service import OrderService

router = APIRouter()


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Atomically ingest customer order: verifies stock availability and reserves items idempotently.
    """
    order = await OrderService.create_order(db=db, order_in=order_in, channel=order_in.channel)
    return order


@router.get("/", response_model=List[OrderResponse])
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List orders with filtering and pagination."""
    stmt = select(Order).order_by(desc(Order.created_at))
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if channel:
        stmt = stmt.where(Order.channel == channel)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_by_id(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve order details with line items."""
    stmt = select(Order).where(Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


@router.post("/{order_id}/fulfill", response_model=OrderResponse)
async def fulfill_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fulfill order: releases reserved counters, debits on-hand inventory via SALE transactions."""
    return await OrderService.fulfill_order(db=db, order_id=order_id)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel order: releases reserved stock back to available pool."""
    return await OrderService.cancel_order(db=db, order_id=order_id)


@router.post("/webhook/shopify", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def shopify_webhook_ingest(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None, alias="X-Shopify-Hmac-Sha256"),
    warehouse_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Shopify-style orders/create webhook ingestion:
    Validates HMAC-SHA256 signature, deduplicates idempotency token, atomically reserves stock.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    return await OrderService.process_shopify_webhook(
        db=db,
        raw_body=raw_body,
        hmac_header=x_shopify_hmac_sha256,
        payload=payload,
        warehouse_id=warehouse_id
    )
