from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.alert import Alert
from backend.app.models.user import User
from backend.app.schemas.alert import (
    AlertResolveRequest,
    AlertResponse,
    AnomalyAuditResponse,
)
from backend.app.services.anomaly_service import AnomalyDetectionService

router = APIRouter()


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    status_filter: Optional[str] = Query("OPEN", alias="status"),
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List system exception alerts (Drift, Spikes, Dead Stock, Delays, Reviews)."""
    stmt = select(Alert).order_by(desc(Alert.created_at))
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    resolve_in: AlertResolveRequest = AlertResolveRequest(),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Human manager marks an exception alert as resolved."""
    stmt = select(Alert).where(Alert.id == alert_id)
    res = await db.execute(stmt)
    alert = res.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")

    alert.status = "RESOLVED"
    alert.resolved_at = datetime.now(timezone.utc)
    if resolve_in.resolution_notes:
        ctx = dict(alert.context_data or {})
        ctx["resolution_notes"] = resolve_in.resolution_notes
        ctx["resolved_by"] = admin_user.email
        alert.context_data = ctx

    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/audit", response_model=AnomalyAuditResponse)
async def run_anomaly_audit(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    On-Demand Anomaly Sweep:
    Audits stock drift, demand spikes (>3σ), dead stock (>60 days), negative balances, and supplier delays.
    """
    return await AnomalyDetectionService.run_full_anomaly_audit(db=db)

