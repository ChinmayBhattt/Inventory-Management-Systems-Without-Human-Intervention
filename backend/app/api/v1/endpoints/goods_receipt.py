from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.api.deps import get_current_user, get_db, require_admin
from backend.app.models.user import User
from backend.app.schemas.goods_receipt import (
    GoodsReceiptRequest,
    GoodsReceiptResponse,
)
from backend.app.services.goods_receipt_service import GoodsReceiptService

router = APIRouter()


@router.post("/", response_model=GoodsReceiptResponse, status_code=status.HTTP_201_CREATED)
async def process_goods_receipt(
    receipt_in: GoodsReceiptRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    """
    Ingest Goods Receipt Note (GRN) or ASN webhook:
    Atomically updates event-sourced ledger, decrements on_order, increments on_hand, and advances PO status.
    """
    return await GoodsReceiptService.process_receipt(db=db, receipt_in=receipt_in)

