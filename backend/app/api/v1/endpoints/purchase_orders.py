import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.user import User
from backend.app.schemas.purchase_order import POApprovalRequest, PurchaseOrderResponse
from backend.app.services.replenishment_service import ReplenishmentService

router = APIRouter()


@router.get("/", response_model=List[PurchaseOrderResponse])
async def list_purchase_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    supplier_id: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List purchase orders across statuses (AUTO_APPROVED, NEEDS_REVIEW, SENT, etc.)."""
    stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).order_by(desc(PurchaseOrder.created_at))
    if status_filter:
        stmt = stmt.where(PurchaseOrder.status == status_filter)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if warehouse_id:
        stmt = stmt.where(PurchaseOrder.warehouse_id == warehouse_id)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/{po_id}", response_model=PurchaseOrderResponse)
async def get_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve details and items for a specific purchase order."""
    stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.id == po_id)
    res = await db.execute(stmt)
    po = res.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")
    return po


@router.get("/{po_id}/pdf")
async def download_po_pdf(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download/preview vector PDF document for a purchase order."""
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id)
    res = await db.execute(stmt)
    po = res.scalar_one_or_none()
    if not po or not po.pdf_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PO PDF document not found.")

    if not os.path.exists(po.pdf_storage_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF file does not exist on disk.")

    return FileResponse(
        path=po.pdf_storage_path,
        media_type="application/pdf",
        filename=f"{po.po_number}.pdf"
    )


@router.post("/{po_id}/approve", response_model=PurchaseOrderResponse)
async def approve_purchase_order(
    po_id: str,
    approval_in: POApprovalRequest = POApprovalRequest(),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Human manager approval for purchase orders requiring review."""
    po = await ReplenishmentService.manual_approve_po(db=db, po_id=po_id, notes=approval_in.notes)
    return po


@router.post("/{po_id}/cancel", response_model=PurchaseOrderResponse)
async def cancel_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Cancel purchase order and release on_order allocation."""
    po = await ReplenishmentService.cancel_po(db=db, po_id=po_id)
    return po

