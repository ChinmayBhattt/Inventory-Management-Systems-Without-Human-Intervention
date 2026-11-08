import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.stock_level import StockLevel
from backend.app.models.supplier import Supplier
from backend.app.models.warehouse import Warehouse
from backend.app.models.product import Product
from backend.app.models.reorder_policy import ReorderPolicy


@pytest.mark.asyncio
async def test_complete_autonomous_inventory_lifecycle_e2e(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    End-to-End System Test:
    1. Register Supplier & Warehouse.
    2. Register Product SKU.
    3. Configure Autonomous Reorder Policy.
    4. Inbound Goods Receipt Note (GRN) opening balance.
    5. Customer Order Ingestion & Reservation.
    6. Customer Order Fulfillment.
    7. Shopify Webhook Ingestion with HMAC-SHA256 signature.
    8. Autonomous ROP Evaluation & Auto-Approved PO Generation with Vector PDF.
    9. Supplier Dispatch via Gateway.
    10. Supplier Acknowledgment (ACK) with tracking number.
    11. Goods Receipt of Replenishment Shipment (advances to COMPLETED).
    12. Invariant & Zero-Drift Verification.
    """
    # --- Step 1: Create Supplier & Warehouse ---
    supp_resp = await async_client.post(
        "/api/v1/suppliers/",
        json={
            "name": "OmniSupply Global",
            "email": "orders@omnisupply.com",
            "api_endpoint": "https://api.omnisupply.com/v1/orders",
            "lead_time_days": 5,
            "minimum_order_value": "200.00",
            "reliability_score": 0.98,
        },
        headers=auth_headers
    )
    assert supp_resp.status_code == 201
    supplier_id = supp_resp.json()["id"]

    wh = Warehouse(code=f"WH-E2E-{uuid.uuid4().hex[:4]}", name="E2E Main Hub", address="100 E2E Blvd")
    prod = Product(
        sku=f"SKU-E2E-{uuid.uuid4().hex[:4]}",
        name="Ultra High-Speed USB Hub",
        category="Electronics",
        unit_cost=Decimal("20.00"),
        unit_price=Decimal("45.00"),
        default_supplier_id=supplier_id
    )
    db_session.add_all([wh, prod])
    await db_session.commit()
    warehouse_id = wh.id
    product_id = prod.id

    # --- Step 3: Configure Reorder Policy ---
    # ROP = 30, EOQ = 50, Auto-Approve max = $5000
    pol_resp = await async_client.post(
        "/api/v1/replenishment/policies",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "service_level_z": 1.65,
            "lead_time_days": 5,
            "holding_cost_annual_pct": 0.20,
            "fixed_order_cost": "50.00",
            "auto_approve_max_po_value": "5000.00",
            "is_autonomous": True
        },
        headers=auth_headers
    )
    assert pol_resp.status_code == 201
    policy_id = pol_resp.json()["id"]

    # Directly set explicit policy targets for predictable trigger testing
    policy_stmt = await db_session.execute(select(ReorderPolicy).where(ReorderPolicy.id == policy_id))
    pol_obj = policy_stmt.scalar_one()
    pol_obj.reorder_point = 35
    pol_obj.economic_order_quantity = 50
    pol_obj.safety_stock = 15
    await db_session.commit()

    # --- Step 4: Initial Goods Receipt (Opening Stock of 50 units) ---
    grn_init_resp = await async_client.post(
        "/api/v1/ledger/adjustment",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": 50,
            "adjustment_type": "ADJUSTMENT",
            "reason": "Initial warehouse inventory load",
            "idempotency_key": f"e2e_init_{uuid.uuid4().hex}"
        },
        headers=auth_headers
    )
    assert grn_init_resp.status_code in (200, 201)
    assert grn_init_resp.json()["quantity_delta"] == 50

    stock_res = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={product_id}&warehouse_id={warehouse_id}",
        headers=auth_headers
    )
    assert stock_res.status_code == 200
    stock_data = stock_res.json()[0]
    assert stock_data["on_hand"] == 50
    assert stock_data["available"] == 50

    # --- Step 5: Customer Order Ingestion (Order 1: 15 units) ---
    order1_payload = {
        "order_number": f"ORD-E2E-{uuid.uuid4().hex[:6].upper()}",
        "warehouse_id": warehouse_id,
        "items": [
            {"product_id": product_id, "quantity": 15, "unit_price": "45.00"}
        ],
        "idempotency_key": f"idem_ord1_{uuid.uuid4().hex}"
    }
    ord1_resp = await async_client.post("/api/v1/orders/", json=order1_payload, headers=auth_headers)
    assert ord1_resp.status_code == 201
    order1_data = ord1_resp.json()
    assert order1_data["status"] == "RESERVED"

    # Verify atomic reservation: on_hand=50, reserved=15, available=35
    stock_res = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={product_id}&warehouse_id={warehouse_id}",
        headers=auth_headers
    )
    stock_data = stock_res.json()[0]
    assert stock_data["on_hand"] == 50
    assert stock_data["reserved"] == 15
    assert stock_data["available"] == 35

    # --- Step 6: Order 1 Fulfillment ---
    fulfill1_resp = await async_client.post(f"/api/v1/orders/{order1_data['id']}/fulfill", headers=auth_headers)
    assert fulfill1_resp.status_code == 200
    assert fulfill1_resp.json()["status"] == "FULFILLED"

    stock_res = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={product_id}&warehouse_id={warehouse_id}",
        headers=auth_headers
    )
    stock_data = stock_res.json()[0]
    assert stock_data["on_hand"] == 35
    assert stock_data["reserved"] == 0
    assert stock_data["available"] == 35

    # --- Step 7: Shopify Webhook Order (Order 2: 10 units via webhook) ---
    shopify_order_payload = {
        "id": 987654321,
        "name": f"#SHOPIFY-E2E-{uuid.uuid4().hex[:4]}",
        "financial_status": "paid",
        "warehouse_id": warehouse_id,
        "line_items": [
            {
                "sku": prod.sku,
                "quantity": 10,
                "price": "45.00"
            }
        ]
    }
    raw_body = json.dumps(shopify_order_payload).encode("utf-8")
    digest = hmac.new(
        settings.SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).digest()
    signature = base64.b64encode(digest).decode("utf-8")

    hook_resp = await async_client.post(
        "/api/v1/orders/webhook/shopify",
        content=raw_body,
        headers={
            "X-Shopify-Hmac-Sha256": signature,
            "Content-Type": "application/json"
        }
    )
    assert hook_resp.status_code == 201
    assert hook_resp.json()["status"] == "RESERVED"

    # Fulfill Shopify order
    shopify_order_id = hook_resp.json()["id"]
    await async_client.post(f"/api/v1/orders/{shopify_order_id}/fulfill", headers=auth_headers)

    # Current stock state: on_hand = 25, available = 25, ROP = 35
    # Since available (25) <= ROP (35), REORDER POINT IS TRIGGERED!
    stock_res = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={product_id}&warehouse_id={warehouse_id}",
        headers=auth_headers
    )
    stock_data = stock_res.json()[0]
    assert stock_data["on_hand"] == 25
    assert stock_data["available"] == 25

    # --- Step 8: Autonomous ROP Replenishment Evaluation ---
    sweep_resp = await async_client.post("/api/v1/replenishment/evaluate", headers=auth_headers)
    assert sweep_resp.status_code == 200
    sweep_data = sweep_resp.json()
    assert sweep_data["purchase_orders_created"] >= 1

    # Find the generated PO
    po_list_resp = await async_client.get("/api/v1/purchase-orders/", headers=auth_headers)
    assert po_list_resp.status_code == 200
    pos = [p for p in po_list_resp.json() if p["warehouse_id"] == warehouse_id and p["supplier_id"] == supplier_id]
    assert len(pos) >= 1
    po = pos[0]
    assert po["status"] == "AUTO_APPROVED"
    assert po["approval_mode"] == "AUTONOMOUS"
    assert po["pdf_storage_path"] is not None

    # on_order should be allocated: 25 on_hand + 50 on_order = 75 effective stock
    stock_res = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={product_id}&warehouse_id={warehouse_id}",
        headers=auth_headers
    )
    stock_data = stock_res.json()[0]
    assert stock_data["on_order"] >= 50

    # --- Step 9: Supplier Dispatch via Gateway ---
    disp_resp = await async_client.post(f"/api/v1/suppliers/dispatch-po/{po['id']}", headers=auth_headers)
    assert disp_resp.status_code == 200
    assert disp_resp.json()["status"] == "SENT"

    # --- Step 10: Inbound Supplier Acknowledgment Webhook ---
    confirmed_date = datetime.now(timezone.utc) + timedelta(days=4)
    ack_resp = await async_client.post(
        "/api/v1/suppliers/po-acknowledgment",
        json={
            "po_number": po["po_number"],
            "confirmed_delivery_date": confirmed_date.isoformat(),
            "tracking_number": "TRACK-E2E-12345",
            "notes": "Freight in transit."
        }
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "CONFIRMED"

    # --- Step 11: Inbound Goods Receipt of Shipment ---
    qty_ordered = po["items"][0]["quantity_ordered"]
    grn_resp = await async_client.post(
        "/api/v1/goods-receipt/",
        json={
            "po_number": po["po_number"],
            "warehouse_id": warehouse_id,
            "items": [
                {"product_id": product_id, "quantity_received": qty_ordered, "condition": "GOOD"}
            ]
        },
        headers=auth_headers
    )
    assert grn_resp.status_code == 201
    assert grn_resp.json()["po_status"] == "COMPLETED"

    # Final stock: 25 previous + qty_ordered received, on_order = 0
    stock_res = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={product_id}&warehouse_id={warehouse_id}",
        headers=auth_headers
    )
    stock_data = stock_res.json()[0]
    assert stock_data["on_hand"] == 25 + qty_ordered
    assert stock_data["available"] == 25 + qty_ordered
    assert stock_data["on_order"] == 0

    # --- Step 12: Zero-Drift & Anomaly Audit Sweep Verification ---
    audit_resp = await async_client.post("/api/v1/alerts/audit", headers=auth_headers)
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["stock_drift_count"] == 0
    assert audit_data["negative_stock_count"] if "negative_stock_count" in audit_data else True


@pytest.mark.asyncio
async def test_e2e_needs_review_po_and_human_manager_approval(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    E2E Test: Threshold Exception Escalation & Human Manager Approval
    1. Create policy with a low auto-approval ceiling ($100).
    2. Replenishment generates a PO totaling $1,000+ -> exceeds ceiling.
    3. System autonomously assigns status NEEDS_REVIEW and raises PO_NEEDS_REVIEW alert.
    4. Human manager reviews and calls POST /api/v1/purchase-orders/{id}/approve.
    5. PO is approved, on_order counter updated, and alert is marked RESOLVED.
    """
    wh = Warehouse(code=f"WH-ESC-{uuid.uuid4().hex[:4]}", name="Escalation Hub")
    supp = Supplier(name=f"Elite Supplier {uuid.uuid4().hex[:4]}", email="orders@elitesupplier.com", lead_time_days=4)
    db_session.add_all([wh, supp])
    await db_session.commit()

    prod = Product(
        sku=f"SKU-EXPENSIVE-{uuid.uuid4().hex[:4]}",
        name="High-Value Sensor",
        category="Electronics",
        unit_cost=Decimal("150.00"),
        unit_price=Decimal("300.00"),
        default_supplier_id=supp.id
    )
    db_session.add(prod)
    await db_session.commit()

    # Create policy with strict $100 ceiling
    policy = ReorderPolicy(
        product_id=prod.id,
        warehouse_id=wh.id,
        reorder_point=40,
        economic_order_quantity=20,  # 20 * $150 = $3,000 >> $100 ceiling
        safety_stock=10,
        auto_approve_max_po_value=Decimal("100.00"),
        is_autonomous=True
    )
    db_session.add(policy)
    await db_session.commit()

    # Trigger replenishment sweep
    sweep_resp = await async_client.post("/api/v1/replenishment/evaluate", headers=auth_headers)
    assert sweep_resp.status_code == 200

    # Verify PO is created with NEEDS_REVIEW status
    po_res = await async_client.get("/api/v1/purchase-orders/", headers=auth_headers)
    assert po_res.status_code == 200
    pos = [p for p in po_res.json() if p["warehouse_id"] == wh.id and p["supplier_id"] == supp.id]
    assert len(pos) >= 1
    flagged_po = pos[0]
    assert flagged_po["status"] == "NEEDS_REVIEW"
    assert flagged_po["approval_mode"] == "MANUAL"

    # Verify Alert was generated for Human Operator
    alerts_resp = await async_client.get("/api/v1/alerts/?alert_type=PO_NEEDS_REVIEW", headers=auth_headers)
    assert alerts_resp.status_code == 200
    matching_alerts = [a for a in alerts_resp.json() if a["product_id"] == prod.id]
    assert len(matching_alerts) >= 1
    alert_id = matching_alerts[0]["id"]
    assert matching_alerts[0]["status"] == "OPEN"

    # Human Manager approves PO
    approve_resp = await async_client.post(
        f"/api/v1/purchase-orders/{flagged_po['id']}/approve",
        json={"notes": "Approved by senior supply chain manager"},
        headers=auth_headers
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] in ("AUTO_APPROVED", "APPROVED")

    # Verify on_order stock is now credited
    stock_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert stock_resp.json()[0]["on_order"] >= 20

    # Verify Alert is now RESOLVED
    alerts_after_resp = await async_client.get(f"/api/v1/alerts/?status=RESOLVED", headers=auth_headers)
    assert any(a["id"] == alert_id for a in alerts_after_resp.json())


@pytest.mark.asyncio
async def test_e2e_shopify_webhook_idempotency_replay(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    E2E Test: Shopify Webhook Idempotency & Replay Protection
    Sending identical webhook twice must return the same order without double-reserving inventory.
    """
    wh = Warehouse(code=f"WH-SHOPIFY-{uuid.uuid4().hex[:4]}", name="Shopify Fulfill Hub", is_active=True)
    prod = Product(
        sku=f"SKU-IDEM-{uuid.uuid4().hex[:4]}",
        name="Wireless Earbuds",
        category="Electronics",
        unit_cost=Decimal("25.00"),
        unit_price=Decimal("60.00")
    )
    db_session.add_all([wh, prod])
    await db_session.commit()

    # Load 100 opening inventory
    await async_client.post(
        "/api/v1/ledger/adjustment",
        json={
            "product_id": prod.id,
            "warehouse_id": wh.id,
            "quantity_delta": 100,
            "adjustment_type": "ADJUSTMENT",
            "reason": "Initial stock load",
            "idempotency_key": f"load_{uuid.uuid4().hex}"
        },
        headers=auth_headers
    )

    shopify_payload = {
        "id": 1122334455,
        "name": f"#REPLAY-{uuid.uuid4().hex[:4]}",
        "financial_status": "paid",
        "warehouse_id": wh.id,
        "line_items": [
            {"sku": prod.sku, "quantity": 12, "price": "60.00"}
        ]
    }
    raw_body = json.dumps(shopify_payload).encode("utf-8")
    digest = hmac.new(
        settings.SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).digest()
    sig = base64.b64encode(digest).decode("utf-8")

    # First Webhook Delivery
    resp1 = await async_client.post(
        f"/api/v1/orders/webhook/shopify?warehouse_id={wh.id}",
        content=raw_body,
        headers={"X-Shopify-Hmac-Sha256": sig, "Content-Type": "application/json"}
    )
    assert resp1.status_code == 201
    order1 = resp1.json()

    # Check stock reservation: reserved=12, available=88
    stock1_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    stock1 = stock1_resp.json()[0]
    assert stock1["reserved"] == 12
    assert stock1["available"] == 88

    # Replay identical Webhook (simulating network duplicate)
    resp2 = await async_client.post(
        f"/api/v1/orders/webhook/shopify?warehouse_id={wh.id}",
        content=raw_body,
        headers={"X-Shopify-Hmac-Sha256": sig, "Content-Type": "application/json"}
    )
    assert resp2.status_code in (200, 201)
    order2 = resp2.json()
    assert order2["id"] == order1["id"]

    # Stock must remain unchanged: NOT double deducted
    stock2_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    stock2 = stock2_resp.json()[0]
    assert stock2["reserved"] == 12
    assert stock2["available"] == 88


@pytest.mark.asyncio
async def test_e2e_stock_drift_detection_and_auto_correction(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    E2E Test: Stock Drift Anomaly Detection & Ledger Self-Healing Auto-Correction
    1. Seed legitimate transactions totaling 50 units.
    2. Artificially tamper with cached materialized stock_levels (simulate cache corruption/drift).
    3. Run audit sweep -> detects drift, raises alert.
    4. Call ledger reconciliation endpoint with auto_correct=True.
    5. Cache is restored to true integral sum and drift is eliminated.
    """
    wh = Warehouse(code=f"WH-DRIFT-{uuid.uuid4().hex[:4]}", name="Drift Test Hub")
    prod = Product(
        sku=f"SKU-DRIFT-{uuid.uuid4().hex[:4]}",
        name="Precision Sensor",
        category="Electronics",
        unit_cost=Decimal("10.00"),
        unit_price=Decimal("20.00")
    )
    db_session.add_all([wh, prod])
    await db_session.commit()

    # Record 50 units via ledger
    await async_client.post(
        "/api/v1/ledger/adjustment",
        json={
            "product_id": prod.id,
            "warehouse_id": wh.id,
            "quantity_delta": 50,
            "adjustment_type": "ADJUSTMENT",
            "reason": "Legitimate transaction",
            "idempotency_key": f"legit_{uuid.uuid4().hex}"
        },
        headers=auth_headers
    )

    # Artificially tamper with stock_levels cache (set to 999 instead of 50)
    stock_stmt = await db_session.execute(
        select(StockLevel).where(StockLevel.product_id == prod.id, StockLevel.warehouse_id == wh.id)
    )
    stock_record = stock_stmt.scalar_one()
    stock_record.on_hand = 999
    await db_session.commit()

    # Run audit sweep -> detects disparity
    audit_resp = await async_client.post("/api/v1/alerts/audit", headers=auth_headers)
    assert audit_resp.status_code == 200
    assert audit_resp.json()["stock_drift_count"] >= 1

    # Call reconciliation with auto_correct=True
    reconcile_resp = await async_client.post(
        f"/api/v1/ledger/reconcile?product_id={prod.id}&warehouse_id={wh.id}&auto_correct=true",
        headers=auth_headers
    )
    assert reconcile_resp.status_code == 200
    reconcile_data = reconcile_resp.json()
    assert reconcile_data["cached_on_hand"] == 999
    assert reconcile_data["ledger_sum_on_hand"] == 50
    assert reconcile_data["discrepancy"] == 949
    assert reconcile_data["is_synchronized"] is False

    # Verify cache is now restored to 50
    final_stock = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert final_stock.json()[0]["on_hand"] == 50
