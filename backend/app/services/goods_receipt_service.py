from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.logging import logger
from backend.app.models.alert import Alert
from backend.app.models.purchase_order import POItem, PurchaseOrder
from backend.app.models.stock_level import StockLevel
from backend.app.schemas.goods_receipt import (
    GoodsReceiptRequest,
    GoodsReceiptResponse,
    ReceivedItemResult,
)
from backend.app.services.ledger_service import InventoryLedgerService


class GoodsReceiptService:
    @staticmethod
    async def process_receipt(
        db: AsyncSession,
        receipt_in: GoodsReceiptRequest
    ) -> GoodsReceiptResponse:
        """
        Process Inbound Goods Receipt Note (GRN):
        1. Validates PO status.
        2. Crediting ledger with RECEIPT events.
        3. Decrementing on_order, incrementing on_hand.
        4. Reconciling partial vs complete receipt.
        """
        stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(
            PurchaseOrder.po_number == receipt_in.po_number
        )
        res = await db.execute(stmt)
        po = res.scalar_one_or_none()

        if not po:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PO {receipt_in.po_number} not found.")

        if po.status in ["COMPLETED", "CANCELLED"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot receive goods for PO in {po.status} status."
            )

        grn_number = receipt_in.grn_number or f"GRN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        item_results: List[ReceivedItemResult] = []

        po_items_map = {item.product_id: item for item in po.items}

        for item_in in receipt_in.items:
            po_item = po_items_map.get(item_in.product_id)
            if not po_item:
                logger.warning(f"GRN received item {item_in.product_id} not in PO {po.po_number}")
                continue

            qty = item_in.quantity_received
            condition = item_in.condition.upper()

            if condition == "GOOD":
                # 1. Record immutable RECEIPT transaction in ledger
                tx_idem = f"grn_{grn_number}_{item_in.product_id}"
                tx, stock = await InventoryLedgerService.record_transaction(
                    db=db,
                    product_id=item_in.product_id,
                    warehouse_id=receipt_in.warehouse_id,
                    transaction_type="RECEIPT",
                    quantity_delta=qty,
                    reference_type="PURCHASE_ORDER",
                    reference_id=po.po_number,
                    idempotency_key=tx_idem,
                    metadata_json={
                        "grn_number": grn_number,
                        "lot_number": item_in.lot_number,
                        "condition": "GOOD"
                    }
                )

                # 2. Decrement on_order allocation
                stock.on_order = max(0, stock.on_order - qty)
                po_item.quantity_received += qty
                await db.flush()

                item_results.append(
                    ReceivedItemResult(
                        product_id=item_in.product_id,
                        quantity_received=qty,
                        condition="GOOD",
                        transaction_id=tx.id,
                        new_on_hand=stock.on_hand,
                        new_on_order=stock.on_order
                    )
                )

            elif condition == "DAMAGED":
                # Damaged goods received: record damage write-off & create supplier dispute alert
                logger.warning(f"Damaged goods received on {po.po_number}: {qty} units of SKU {item_in.product_id}")
                tx_dmg_idem = f"grn_damaged_{grn_number}_{item_in.product_id}"
                tx, stock = await InventoryLedgerService.record_transaction(
                    db=db,
                    product_id=item_in.product_id,
                    warehouse_id=receipt_in.warehouse_id,
                    transaction_type="DAMAGE",
                    quantity_delta=0,  # Zero delta as it never enters usable on_hand
                    reference_type="PURCHASE_ORDER_DAMAGE",
                    reference_id=po.po_number,
                    idempotency_key=tx_dmg_idem,
                    metadata_json={"condition": "DAMAGED", "grn": grn_number}
                )
                stock.on_order = max(0, stock.on_order - qty)
                await db.flush()

                # Raise dispute alert
                alert = Alert(
                    alert_type="SUPPLIER_DELAY",
                    severity="CRITICAL",
                    product_id=item_in.product_id,
                    warehouse_id=receipt_in.warehouse_id,
                    message=f"Damaged inventory received: {qty} units on PO {po.po_number}. Dispute required.",
                    context_data={"po_number": po.po_number, "quantity_damaged": qty},
                    status="OPEN"
                )
                db.add(alert)

                item_results.append(
                    ReceivedItemResult(
                        product_id=item_in.product_id,
                        quantity_received=qty,
                        condition="DAMAGED",
                        transaction_id=tx.id,
                        new_on_hand=stock.on_hand,
                        new_on_order=stock.on_order
                    )
                )

        # 3. Check PO Completion
        all_completed = all(it.quantity_received >= it.quantity_ordered for it in po.items)
        po.status = "COMPLETED" if all_completed else "PARTIALLY_RECEIVED"

        await db.commit()
        await db.refresh(po)

        logger.info(f"GRN {grn_number} processed for {po.po_number}. New PO status: {po.status}")

        return GoodsReceiptResponse(
            grn_number=grn_number,
            po_number=po.po_number,
            po_status=po.status,
            warehouse_id=receipt_in.warehouse_id,
            items_received=item_results,
            received_at=datetime.now(timezone.utc)
        )

