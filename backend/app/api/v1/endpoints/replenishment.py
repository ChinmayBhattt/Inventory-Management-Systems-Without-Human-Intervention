from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.reorder_policy import ReorderPolicy
from backend.app.models.user import User
from backend.app.models.warehouse import Warehouse
from backend.app.schemas.replenishment import (
    ReorderPolicyCreate,
    ReorderPolicyResponse,
    ReorderPolicyUpdate,
    ReplenishmentEvaluationItem,
    ReplenishmentRunResponse,
)
from backend.app.services.replenishment_service import ReplenishmentService

router = APIRouter()


@router.post("/evaluate", response_model=ReplenishmentRunResponse)
async def evaluate_all_replenishment(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    Autonomous Replenishment Sweep:
    Evaluates Effective Stock <= ROP across all active inventory and triggers PO generation.
    """
    return await ReplenishmentService.evaluate_all_replenishment(db=db)


@router.post("/evaluate/{product_id}", response_model=ReplenishmentEvaluationItem)
async def evaluate_product_replenishment(
    product_id: str,
    warehouse_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Evaluate replenishment for a specific product and warehouse."""
    if not warehouse_id:
        wh_res = await db.execute(select(Warehouse).where(Warehouse.is_active == True).limit(1))
        wh = wh_res.scalar_one_or_none()
        warehouse_id = wh.id if wh else None

    return await ReplenishmentService.evaluate_product_replenishment(
        db=db,
        product_id=product_id,
        warehouse_id=warehouse_id
    )


@router.post("/policies", response_model=ReorderPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_reorder_policy(
    policy_in: ReorderPolicyCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Create or initialize stochastic inventory reorder policy."""
    policy = await ReplenishmentService.get_or_create_policy(
        db=db,
        product_id=policy_in.product_id,
        warehouse_id=policy_in.warehouse_id
    )
    policy.service_level_z = policy_in.service_level_z
    policy.lead_time_days = policy_in.lead_time_days
    policy.holding_cost_annual_pct = policy_in.holding_cost_annual_pct
    policy.fixed_order_cost = policy_in.fixed_order_cost
    policy.auto_approve_max_po_value = policy_in.auto_approve_max_po_value
    policy.is_autonomous = policy_in.is_autonomous
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/policies", response_model=List[ReorderPolicyResponse])
async def list_reorder_policies(
    product_id: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List stochastic inventory replenishment policies and calculated targets (SS, ROP, EOQ)."""
    stmt = select(ReorderPolicy)
    if product_id:
        stmt = stmt.where(ReorderPolicy.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(ReorderPolicy.warehouse_id == warehouse_id)

    res = await db.execute(stmt)
    return res.scalars().all()


@router.put("/policies/{policy_id}", response_model=ReorderPolicyResponse)
async def update_reorder_policy(
    policy_id: str,
    policy_in: ReorderPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """Update stochastic inventory policy settings (Z-factor, lead time, holding cost %, order cost, auto-approval limit)."""
    stmt = select(ReorderPolicy).where(ReorderPolicy.id == policy_id)
    res = await db.execute(stmt)
    policy = res.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reorder policy not found.")

    update_data = policy_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(policy, field, val)

    await db.commit()
    await db.refresh(policy)
    return policy

