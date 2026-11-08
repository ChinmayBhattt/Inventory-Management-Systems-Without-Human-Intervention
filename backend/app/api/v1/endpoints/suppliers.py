from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.supplier import Supplier
from backend.app.models.user import User
from backend.app.schemas.purchase_order import PurchaseOrderResponse
from backend.app.schemas.supplier import (
    POAcknowledgmentRequest,
    PODispatchResponse,
    SupplierCreate,
    SupplierResponse,
)
from backend.app.services.supplier_gateway import SupplierGatewayService

router = APIRouter()


@router.get("/", response_model=List[SupplierResponse])
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List registered inventory suppliers and vendor profiles."""
    res = await db.execute(select(Supplier))
    return res.scalars().all()


@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    supp_in: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Create new supplier profile with lead times and reliability scoring."""
    supplier = Supplier(
        name=supp_in.name,
        email=supp_in.email,
        api_endpoint=supp_in.api_endpoint,
        lead_time_days=supp_in.lead_time_days,
        minimum_order_value=supp_in.minimum_order_value,
        reliability_score=supp_in.reliability_score
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


@router.post("/dispatch-po/{po_id}", response_model=PODispatchResponse)
async def dispatch_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    Dispatch approved Purchase Order to supplier via Gateway (REST API adapter or SMTP email).
    """
    return await SupplierGatewayService.dispatch_purchase_order(db=db, po_id=po_id)


@router.post("/po-acknowledgment", response_model=PurchaseOrderResponse)
async def supplier_po_acknowledgment(
    ack_in: POAcknowledgmentRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Inbound supplier confirmation webhook:
    Updates confirmed delivery date (ETA) and transitions status to CONFIRMED.
    """
    return await SupplierGatewayService.acknowledge_po(
        db=db,
        po_number=ack_in.po_number,
        confirmed_delivery_date=ack_in.confirmed_delivery_date,
        tracking_number=ack_in.tracking_number,
        notes=ack_in.notes
    )

