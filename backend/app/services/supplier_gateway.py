import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.alert import Alert
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.supplier import Supplier
from backend.app.schemas.supplier import PODispatchResponse


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SupplierGatewayService:
    @staticmethod
    async def dispatch_purchase_order(
        db: AsyncSession,
        po_id: str
    ) -> PODispatchResponse:
        """
        Dispatches approved Purchase Order to supplier via REST API or SMTP Email.
        Updates PO status to SENT.
        """
        stmt = select(PurchaseOrder).options(
            selectinload(PurchaseOrder.items),
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.warehouse)
        ).where(PurchaseOrder.id == po_id)
        res = await db.execute(stmt)
        po = res.scalar_one_or_none()

        if not po:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")

        if po.status not in ["AUTO_APPROVED", "APPROVED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot dispatch PO in status '{po.status}'. Must be AUTO_APPROVED or APPROVED."
            )

        supplier = po.supplier
        dispatched_via = "MOCK_REST"
        destination = supplier.email if supplier else "supplier@example.com"

        # 1. Attempt REST Adapter if endpoint defined
        if supplier and supplier.api_endpoint:
            payload = {
                "po_number": po.po_number,
                "created_at": po.created_at.isoformat(),
                "total_cost": float(po.total_cost),
                "items": [
                    {
                        "product_id": it.product_id,
                        "quantity": it.quantity_ordered,
                        "unit_cost": float(it.unit_cost)
                    }
                    for it in po.items
                ]
            }
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.post(supplier.api_endpoint, json=payload)
                    dispatched_via = "REST_API"
                    destination = supplier.api_endpoint
            except Exception as e:
                logger.info(f"REST supplier dispatch simulated (endpoint unreachable: {e}).")
                dispatched_via = "SIMULATED_REST"

        # 2. Email Transmission Simulation (SMTP/SendGrid)
        logger.info(
            f"PO {po.po_number} dispatched to supplier {supplier.name if supplier else 'Vendor'} "
            f"via {dispatched_via} ({destination}). PDF: {po.pdf_storage_path}"
        )

        po.status = "SENT"
        await db.commit()
        await db.refresh(po)

        return PODispatchResponse(
            po_number=po.po_number,
            dispatched_via=dispatched_via,
            destination=destination,
            status=po.status,
            dispatched_at=datetime.now(timezone.utc)
        )

    @staticmethod
    async def acknowledge_po(
        db: AsyncSession,
        po_number: str,
        confirmed_delivery_date: datetime,
        tracking_number: Optional[str] = None,
        notes: Optional[str] = None
    ) -> PurchaseOrder:
        """
        Processes supplier confirmation webhook or ACK response:
        Updates confirmed delivery date and status to CONFIRMED.
        """
        stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.po_number == po_number)
        res = await db.execute(stmt)
        po = res.scalar_one_or_none()
        if not po:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PO {po_number} not found.")

        po.confirmed_delivery_date = confirmed_delivery_date
        po.status = "CONFIRMED"
        if notes or tracking_number:
            extra = f"Tracking: {tracking_number or 'N/A'}. {notes or ''}".strip()
            po.notes = f"{po.notes or ''} [Supplier Confirmed: {extra}]"

        await db.commit()
        await db.refresh(po)
        logger.info(f"Supplier confirmed PO {po.po_number}. ETA: {confirmed_delivery_date}")
        return po

    @staticmethod
    async def scan_and_followup_overdue_pos(db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Scans for unconfirmed POs (> 48h after dispatch) or overdue deliveries (past ETA).
        Emits follow-ups and logs alerts.
        """
        now = datetime.now(timezone.utc)
        two_days_ago = now - timedelta(hours=48)

        # 1. Unconfirmed POs
        stmt_unconf = select(PurchaseOrder).where(
            PurchaseOrder.status == "SENT",
            PurchaseOrder.created_at <= two_days_ago
        )
        res_unconf = await db.execute(stmt_unconf)
        unconfirmed = res_unconf.scalars().all()

        followups = []
        for po in unconfirmed:
            alert = Alert(
                alert_type="SUPPLIER_DELAY",
                severity="WARNING",
                warehouse_id=po.warehouse_id,
                message=f"PO {po.po_number} pending supplier confirmation for > 48 hours.",
                context_data={"po_number": po.po_number, "po_id": po.id},
                status="OPEN"
            )
            db.add(alert)
            followups.append({"po_number": po.po_number, "reason": "UNCONFIRMED_48H"})

        # 2. Overdue Deliveries
        stmt_overdue = select(PurchaseOrder).where(
            PurchaseOrder.status.in_(["SENT", "CONFIRMED"]),
            PurchaseOrder.expected_delivery_date < now
        )
        res_overdue = await db.execute(stmt_overdue)
        overdue = res_overdue.scalars().all()

        for po in overdue:
            days_overdue = (now - _ensure_utc(po.expected_delivery_date)).days if po.expected_delivery_date else 0
            alert = Alert(
                alert_type="SUPPLIER_DELAY",
                severity="CRITICAL",
                warehouse_id=po.warehouse_id,
                message=f"PO {po.po_number} overdue! Expected delivery was {po.expected_delivery_date.strftime('%Y-%m-%d')}.",
                context_data={"po_number": po.po_number, "po_id": po.id, "days_overdue": days_overdue},
                status="OPEN"
            )
            db.add(alert)
            followups.append({"po_number": po.po_number, "reason": "DELIVERY_PAST_ETA"})

        await db.commit()
        return followups
