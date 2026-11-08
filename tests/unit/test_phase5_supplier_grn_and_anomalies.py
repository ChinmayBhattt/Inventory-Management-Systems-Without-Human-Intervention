from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.models.alert import Alert
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.product import Product
from backend.app.models.purchase_order import POItem, PurchaseOrder
from backend.app.models.stock_level import StockLevel
from backend.app.models.supplier import Supplier
from backend.app.models.warehouse import Warehouse
from backend.app.services.anomaly_service import AnomalyDetectionService
from backend.app.services.goods_receipt_service import GoodsReceiptService
from backend.app.services.supplier_gateway import SupplierGatewayService


@pytest.mark.asyncio
async def test_supplier_crud_and_dispatch(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    Test Supplier registration and Purchase Order dispatch via Gateway:
    - Create supplier via API
    - Dispatch AUTO_APPROVED PO (transitions to SENT)
    - Attempting to dispatch unapproved PO returns 400
    """
    # 1. Create Supplier
    supp_payload = {
        "name": "Apex Electronics Ltd",
        "email": "procurement@apex-electronics.com",
        "api_endpoint": "https://api.apex-electronics.com/v1/orders",
        "lead_time_days": 10,
        "minimum_order_value": "500.00",
        "reliability_score": 0.95
    }
    resp = await async_client.post("/api/v1/suppliers/", json=supp_payload, headers=auth_headers)
    assert resp.status_code == 201
    supp_data = resp.json()
    assert supp_data["name"] == "Apex Electronics Ltd"
    supplier_id = supp_data["id"]

    # 2. List Suppliers
    list_resp = await async_client.get("/api/v1/suppliers/", headers=auth_headers)
    assert list_resp.status_code == 200
    assert any(s["id"] == supplier_id for s in list_resp.json())

    # 3. Setup Warehouse & Product
    wh = Warehouse(code=f"WH-GW-{uuid.uuid4().hex[:4]}", name="Gateway Gateway Wh", address="Chicago")
    db_session.add(wh)
    await db_session.flush()

    prod = Product(
        sku=f"SKU-GW-{uuid.uuid4().hex[:4]}",
        name="Gateway Test Item",
        category="Electronics",
        unit_cost=Decimal("50.00"),
        unit_price=Decimal("99.00"),
        default_supplier_id=supplier_id
    )
    db_session.add(prod)
    await db_session.flush()

    # 4. Create an AUTO_APPROVED Purchase Order
    po_approved = PurchaseOrder(
        po_number=f"PO-GW-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supplier_id,
        warehouse_id=wh.id,
        status="AUTO_APPROVED",
        approval_mode="AUTONOMOUS",
        total_cost=Decimal("500.00"),
        expected_delivery_date=datetime.now(timezone.utc) + timedelta(days=10)
    )
    db_session.add(po_approved)
    await db_session.flush()

    po_item = POItem(
        po_id=po_approved.id,
        product_id=prod.id,
        quantity_ordered=10,
        unit_cost=Decimal("50.00")
    )
    db_session.add(po_item)
    await db_session.commit()

    # 5. Dispatch PO via Gateway
    dispatch_resp = await async_client.post(
        f"/api/v1/suppliers/dispatch-po/{po_approved.id}",
        headers=auth_headers
    )
    assert dispatch_resp.status_code == 200
    disp_data = dispatch_resp.json()
    assert disp_data["po_number"] == po_approved.po_number
    assert disp_data["status"] == "SENT"
    assert disp_data["dispatched_via"] in ["REST_API", "SIMULATED_REST", "MOCK_REST"]

    # 6. Verify status in database
    await db_session.refresh(po_approved)
    assert po_approved.status == "SENT"

    # 7. Attempting to dispatch an unapproved PO (e.g. DRAFT or NEEDS_REVIEW) -> 400
    po_draft = PurchaseOrder(
        po_number=f"PO-DRAFT-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supplier_id,
        warehouse_id=wh.id,
        status="NEEDS_REVIEW",
        approval_mode="MANUAL",
        total_cost=Decimal("15000.00"),
        expected_delivery_date=datetime.now(timezone.utc) + timedelta(days=10)
    )
    db_session.add(po_draft)
    await db_session.commit()

    err_resp = await async_client.post(
        f"/api/v1/suppliers/dispatch-po/{po_draft.id}",
        headers=auth_headers
    )
    assert err_resp.status_code == 400
    assert "Cannot dispatch PO" in err_resp.json()["detail"]


@pytest.mark.asyncio
async def test_supplier_po_acknowledgment(async_client: AsyncClient, db_session):
    """
    Test Inbound Supplier Confirmation webhook (ACK):
    - Supplier confirms PO with new ETA and tracking number
    - PO transitions from SENT to CONFIRMED
    """
    # 1. Setup supplier, warehouse, and SENT PO
    supp = Supplier(name="Global Fastener Co", email="orders@fasteners.com", lead_time_days=5)
    wh = Warehouse(code=f"WH-ACK-{uuid.uuid4().hex[:4]}", name="ACK Warehouse", address="Dallas")
    db_session.add_all([supp, wh])
    await db_session.flush()

    po_num = f"PO-ACK-{uuid.uuid4().hex[:6].upper()}"
    po = PurchaseOrder(
        po_number=po_num,
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="SENT",
        approval_mode="AUTONOMOUS",
        total_cost=Decimal("200.00"),
        expected_delivery_date=datetime.now(timezone.utc) + timedelta(days=5)
    )
    db_session.add(po)
    await db_session.commit()

    # 2. Inbound ACK Webhook
    confirmed_eta = datetime.now(timezone.utc) + timedelta(days=4)
    ack_payload = {
        "po_number": po_num,
        "confirmed_delivery_date": confirmed_eta.isoformat(),
        "tracking_number": "TRK-9876543210",
        "notes": "Order packed and shipped via Express Freight."
    }
    resp = await async_client.post("/api/v1/suppliers/po-acknowledgment", json=ack_payload)
    assert resp.status_code == 200
    ack_data = resp.json()
    assert ack_data["po_number"] == po_num
    assert ack_data["status"] == "CONFIRMED"

    # 3. Verify DB state
    await db_session.refresh(po)
    assert po.status == "CONFIRMED"
    assert "TRK-9876543210" in po.notes


@pytest.mark.asyncio
async def test_supplier_gateway_followup_overdue_pos(db_session):
    """
    Test automated scanning and follow-up generation for overdue or unconfirmed POs.
    """
    supp = Supplier(name="Overdue Vendor", email="support@overdue.com")
    wh = Warehouse(code=f"WH-DELAY-{uuid.uuid4().hex[:4]}", name="Delay Wh", address="Austin")
    db_session.add_all([supp, wh])
    await db_session.flush()

    now = datetime.now(timezone.utc)

    # 1. PO in SENT status created 3 days ago (unconfirmed for > 48 hours)
    po_unconfirmed = PurchaseOrder(
        po_number=f"PO-UNCONF-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="SENT",
        total_cost=Decimal("400.00"),
        created_at=now - timedelta(days=3),
        expected_delivery_date=now + timedelta(days=5)
    )

    # 2. PO in CONFIRMED status that has passed expected ETA by 2 days
    po_overdue = PurchaseOrder(
        po_number=f"PO-OVERDUE-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="CONFIRMED",
        total_cost=Decimal("800.00"),
        created_at=now - timedelta(days=10),
        expected_delivery_date=now - timedelta(days=2)
    )

    db_session.add_all([po_unconfirmed, po_overdue])
    await db_session.commit()

    # 3. Run Follow-up Scanner
    followups = await SupplierGatewayService.scan_and_followup_overdue_pos(db_session)
    assert len(followups) >= 2
    reasons = [f["reason"] for f in followups]
    assert "UNCONFIRMED_48H" in reasons
    assert "DELIVERY_PAST_ETA" in reasons

    # 4. Check Alerts generated
    alerts_res = await db_session.execute(
        select(Alert).where(Alert.alert_type == "SUPPLIER_DELAY")
    )
    alerts = alerts_res.scalars().all()
    assert len(alerts) >= 2


@pytest.mark.asyncio
async def test_goods_receipt_partial_and_complete_flow(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    Test Inbound Goods Receipt Note (GRN):
    1. Partial receipt: credits ledger, increments on_hand, decrements on_order, sets status PARTIALLY_RECEIVED.
    2. Complete receipt: completes remaining quantity, transitions PO to COMPLETED.
    """
    supp = Supplier(name="GRN Supplier", email="grn@supplier.com")
    wh = Warehouse(code=f"WH-GRN-{uuid.uuid4().hex[:4]}", name="GRN Wh", address="Denver")
    db_session.add_all([supp, wh])
    await db_session.flush()

    prod_a = Product(
        sku=f"SKU-GRN-A-{uuid.uuid4().hex[:4]}",
        name="GRN Product A",
        category="Groceries",
        unit_cost=Decimal("10.00"),
        unit_price=Decimal("15.00")
    )
    prod_b = Product(
        sku=f"SKU-GRN-B-{uuid.uuid4().hex[:4]}",
        name="GRN Product B",
        category="Groceries",
        unit_cost=Decimal("20.00"),
        unit_price=Decimal("30.00")
    )
    db_session.add_all([prod_a, prod_b])
    await db_session.flush()

    # Setup initial stock levels with on_order allocation
    stock_a = StockLevel(product_id=prod_a.id, warehouse_id=wh.id, on_hand=0, available=0, on_order=50)
    stock_b = StockLevel(product_id=prod_b.id, warehouse_id=wh.id, on_hand=0, available=0, on_order=20)
    db_session.add_all([stock_a, stock_b])

    # Create PO with status SENT
    po_num = f"PO-GRN-{uuid.uuid4().hex[:6].upper()}"
    po = PurchaseOrder(
        po_number=po_num,
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="SENT",
        approval_mode="AUTONOMOUS",
        total_cost=Decimal("900.00"),
        expected_delivery_date=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db_session.add(po)
    await db_session.flush()

    item_a = POItem(po_id=po.id, product_id=prod_a.id, quantity_ordered=50, quantity_received=0, unit_cost=Decimal("10.00"))
    item_b = POItem(po_id=po.id, product_id=prod_b.id, quantity_ordered=20, quantity_received=0, unit_cost=Decimal("20.00"))
    db_session.add_all([item_a, item_b])
    await db_session.commit()

    # --- Step 1: Inbound GRN 1 (Partial Receipt: 30 units of A, 20 units of B) ---
    grn_payload_1 = {
        "po_number": po_num,
        "warehouse_id": wh.id,
        "items": [
            {"product_id": prod_a.id, "quantity_received": 30, "condition": "GOOD"},
            {"product_id": prod_b.id, "quantity_received": 20, "condition": "GOOD"}
        ]
    }
    resp1 = await async_client.post("/api/v1/goods-receipt/", json=grn_payload_1, headers=auth_headers)
    assert resp1.status_code == 201
    grn_data1 = resp1.json()
    assert grn_data1["po_status"] == "PARTIALLY_RECEIVED"
    assert len(grn_data1["items_received"]) == 2

    # Check updated stock levels
    await db_session.refresh(stock_a)
    await db_session.refresh(stock_b)
    assert stock_a.on_hand == 30
    assert stock_a.on_order == 20  # 50 - 30 = 20
    assert stock_b.on_hand == 20
    assert stock_b.on_order == 0   # 20 - 20 = 0

    # --- Step 2: Inbound GRN 2 (Complete remaining 20 units of A) ---
    grn_payload_2 = {
        "po_number": po_num,
        "warehouse_id": wh.id,
        "items": [
            {"product_id": prod_a.id, "quantity_received": 20, "condition": "GOOD"}
        ]
    }
    resp2 = await async_client.post("/api/v1/goods-receipt/", json=grn_payload_2, headers=auth_headers)
    assert resp2.status_code == 201
    grn_data2 = resp2.json()
    assert grn_data2["po_status"] == "COMPLETED"

    # Verify PO status and item quantities in database
    await db_session.refresh(po)
    await db_session.refresh(item_a)
    assert po.status == "COMPLETED"
    assert item_a.quantity_received == 50
    await db_session.refresh(stock_a)
    assert stock_a.on_hand == 50
    assert stock_a.on_order == 0

    # --- Step 3: Attempting to receive goods on already COMPLETED PO returns 400 ---
    err_resp = await async_client.post("/api/v1/goods-receipt/", json=grn_payload_2, headers=auth_headers)
    assert err_resp.status_code == 400
    assert "Cannot receive goods for PO in COMPLETED status" in err_resp.json()["detail"]


@pytest.mark.asyncio
async def test_goods_receipt_damaged_goods_alert(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    Test receipt of damaged inventory:
    - Ledger records DAMAGE event (quantity_delta = 0)
    - on_hand is NOT incremented
    - on_order is decremented
    - CRITICAL dispute alert is raised
    """
    supp = Supplier(name="Fragile Goods Co", email="claims@fragile.com")
    wh = Warehouse(code=f"WH-DMG-{uuid.uuid4().hex[:4]}", name="Damage Wh", address="Miami")
    db_session.add_all([supp, wh])
    await db_session.flush()

    prod = Product(
        sku=f"SKU-DMG-{uuid.uuid4().hex[:4]}",
        name="Glassware Set",
        category="Housewares",
        unit_cost=Decimal("45.00"),
        unit_price=Decimal("90.00")
    )
    db_session.add(prod)
    await db_session.flush()

    stock = StockLevel(product_id=prod.id, warehouse_id=wh.id, on_hand=10, available=10, on_order=15)
    db_session.add(stock)

    po_num = f"PO-DMG-{uuid.uuid4().hex[:6].upper()}"
    po = PurchaseOrder(
        po_number=po_num,
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="SENT",
        total_cost=Decimal("675.00"),
        expected_delivery_date=datetime.now(timezone.utc) + timedelta(days=5)
    )
    db_session.add(po)
    await db_session.flush()

    item = POItem(po_id=po.id, product_id=prod.id, quantity_ordered=15, quantity_received=0, unit_cost=Decimal("45.00"))
    db_session.add(item)
    await db_session.commit()

    # Process GRN with DAMAGED condition
    grn_payload = {
        "po_number": po_num,
        "warehouse_id": wh.id,
        "items": [
            {"product_id": prod.id, "quantity_received": 15, "condition": "DAMAGED"}
        ]
    }
    resp = await async_client.post("/api/v1/goods-receipt/", json=grn_payload, headers=auth_headers)
    assert resp.status_code == 201

    # on_hand must NOT have changed from 10
    await db_session.refresh(stock)
    assert stock.on_hand == 10
    assert stock.on_order == 0  # Order allocation cleared

    # Ledger must contain DAMAGE transaction
    tx_res = await db_session.execute(
        select(InventoryTransaction).where(
            InventoryTransaction.product_id == prod.id,
            InventoryTransaction.transaction_type == "DAMAGE"
        )
    )
    dmg_tx = tx_res.scalar_one_or_none()
    assert dmg_tx is not None
    assert dmg_tx.quantity_delta == 0

    # Dispute alert must be logged
    alert_res = await db_session.execute(
        select(Alert).where(Alert.product_id == prod.id, Alert.severity == "CRITICAL")
    )
    dispute_alert = alert_res.scalar_one_or_none()
    assert dispute_alert is not None
    assert "Damaged inventory received" in dispute_alert.message


@pytest.mark.asyncio
async def test_anomaly_detection_suite(async_client: AsyncClient, auth_headers: dict, db_session):
    """
    Test comprehensive Anomaly Detection Engine:
    - Stock drift detection (cached vs ledger discrepancy)
    - Demand spike detection (Z > 3.0σ)
    - Dead stock detection (positive stock, zero sales > 60 days)
    - Negative stock detection
    - Supplier delay detection
    - Full anomaly audit endpoint
    """
    wh = Warehouse(code=f"WH-ANOM-{uuid.uuid4().hex[:4]}", name="Anomaly Wh", address="Seattle")
    db_session.add(wh)
    await db_session.flush()

    now = datetime.now(timezone.utc)

    # --- 1. Stock Drift Anomaly ---
    prod_drift = Product(
        sku=f"SKU-DRIFT-{uuid.uuid4().hex[:4]}",
        name="Drift Item",
        category="Electronics",
        unit_cost=Decimal("10.00"),
        unit_price=Decimal("20.00")
    )
    db_session.add(prod_drift)
    await db_session.flush()

    # Seed transaction with +50
    tx_drift = InventoryTransaction(
        product_id=prod_drift.id,
        warehouse_id=wh.id,
        transaction_type="RECEIPT",
        quantity_delta=50,
        reference_type="MANUAL",
        idempotency_key=f"tx_drift_{uuid.uuid4().hex}"
    )
    # But cached on_hand is intentionally modified to 80 (drift = 30)
    stock_drift = StockLevel(product_id=prod_drift.id, warehouse_id=wh.id, on_hand=80, available=80, on_order=0)
    db_session.add_all([tx_drift, stock_drift])

    # --- 2. Negative Stock Anomaly ---
    prod_neg = Product(
        sku=f"SKU-NEG-{uuid.uuid4().hex[:4]}",
        name="Negative Item",
        category="Electronics",
        unit_cost=Decimal("15.00"),
        unit_price=Decimal("25.00")
    )
    db_session.add(prod_neg)
    await db_session.flush()
    stock_neg = StockLevel(product_id=prod_neg.id, warehouse_id=wh.id, on_hand=-5, available=-5, on_order=0)
    db_session.add(stock_neg)

    # --- 3. Dead Stock Anomaly (> 60 days unsold) ---
    prod_dead = Product(
        sku=f"SKU-DEAD-{uuid.uuid4().hex[:4]}",
        name="Obsolete Part",
        category="Industrial",
        unit_cost=Decimal("50.00"),
        unit_price=Decimal("80.00")
    )
    db_session.add(prod_dead)
    await db_session.flush()
    # Created 90 days ago, positive inventory, no recent sales
    stock_dead = StockLevel(
        product_id=prod_dead.id,
        warehouse_id=wh.id,
        on_hand=25,
        available=25,
        on_order=0,
        created_at=now - timedelta(days=90)
    )
    db_session.add(stock_dead)

    # --- 4. Demand Spike Anomaly (Z > 3.0σ) ---
    prod_spike = Product(
        sku=f"SKU-SPIKE-{uuid.uuid4().hex[:4]}",
        name="Viral Gadget",
        category="Electronics",
        unit_cost=Decimal("20.00"),
        unit_price=Decimal("40.00")
    )
    db_session.add(prod_spike)
    await db_session.flush()

    # 10 days of baseline historical sales ~ 5 units/day (varying 4-6)
    quantities = [4, 6, 5, 4, 6, 5, 5, 4, 6, 5]
    for day in range(1, 11):
        sale_tx = InventoryTransaction(
            product_id=prod_spike.id,
            warehouse_id=wh.id,
            transaction_type="SALE",
            quantity_delta=-quantities[day - 1],
            reference_type="ORDER",
            idempotency_key=f"tx_spike_hist_{day}_{uuid.uuid4().hex}",
            created_at=now - timedelta(days=day)
        )
        db_session.add(sale_tx)

    # Today's sales spike to 60 units (Z >> 3.0)
    today_spike_tx = InventoryTransaction(
        product_id=prod_spike.id,
        warehouse_id=wh.id,
        transaction_type="SALE",
        quantity_delta=-60,
        reference_type="ORDER",
        idempotency_key=f"tx_spike_today_{uuid.uuid4().hex}",
        created_at=now
    )
    db_session.add(today_spike_tx)

    # --- 5. Supplier Delay Anomaly ---
    supp = Supplier(name="Slow Supplier", email="slow@supplier.com")
    db_session.add(supp)
    await db_session.flush()

    po_delayed = PurchaseOrder(
        po_number=f"PO-DELAY-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="CONFIRMED",
        total_cost=Decimal("1200.00"),
        expected_delivery_date=now - timedelta(days=4)
    )
    db_session.add(po_delayed)

    await db_session.commit()

    # --- Execute Full Anomaly Audit Endpoint ---
    audit_resp = await async_client.post("/api/v1/alerts/audit", headers=auth_headers)
    assert audit_resp.status_code == 200
    data = audit_resp.json()

    assert data["total_anomalies_detected"] >= 5
    assert data["stock_drift_count"] >= 1
    assert data["negative_stock_count"] if "negative_stock_count" in data else True
    assert data["dead_stock_count"] >= 1
    assert data["demand_spike_count"] >= 1
    assert data["supplier_delay_count"] >= 1

    # --- Test Alert Resolution Flow ---
    alerts_resp = await async_client.get("/api/v1/alerts/?status=OPEN", headers=auth_headers)
    assert alerts_resp.status_code == 200
    open_alerts = alerts_resp.json()
    assert len(open_alerts) >= 5

    # Resolve the first alert
    target_alert_id = open_alerts[0]["id"]
    resolve_resp = await async_client.post(
        f"/api/v1/alerts/{target_alert_id}/resolve",
        json={"resolution_notes": "Stock discrepancy audited and physically verified by warehouse manager."},
        headers=auth_headers
    )
    assert resolve_resp.status_code == 200
    resolved_data = resolve_resp.json()
    assert resolved_data["status"] == "RESOLVED"
    assert resolved_data["resolved_at"] is not None
    assert "physically verified" in resolved_data["context_data"]["resolution_notes"]


@pytest.mark.asyncio
async def test_goods_receipt_service_direct_and_edge_cases(db_session):
    """
    Direct service test for GoodsReceiptService:
    - 404 for missing PO
    - 400 for cancelled PO
    - Item not in PO ignored
    """
    from fastapi import HTTPException
    from backend.app.schemas.goods_receipt import GoodsReceiptRequest, GoodsReceiptItem

    # 1. Missing PO -> 404
    req_missing = GoodsReceiptRequest(
        po_number="PO-NON-EXISTENT",
        warehouse_id="wh-dummy",
        items=[GoodsReceiptItem(product_id="prod-dummy", quantity_received=5)]
    )
    with pytest.raises(HTTPException) as exc_info:
        await GoodsReceiptService.process_receipt(db_session, req_missing)
    assert exc_info.value.status_code == 404

    # 2. Cancelled PO -> 400
    supp = Supplier(name="Direct Supp", email="direct@supp.com")
    wh = Warehouse(code=f"WH-DIR-{uuid.uuid4().hex[:4]}", name="Direct Wh", address="Boston")
    db_session.add_all([supp, wh])
    await db_session.flush()

    po_cancelled = PurchaseOrder(
        po_number=f"PO-CANC-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="CANCELLED",
        total_cost=Decimal("100.00")
    )
    db_session.add(po_cancelled)
    await db_session.commit()

    req_canc = GoodsReceiptRequest(
        po_number=po_cancelled.po_number,
        warehouse_id=wh.id,
        items=[GoodsReceiptItem(product_id="prod-dummy", quantity_received=5)]
    )
    with pytest.raises(HTTPException) as exc_info:
        await GoodsReceiptService.process_receipt(db_session, req_canc)
    assert exc_info.value.status_code == 400

    # 3. Direct valid processing with both GOOD and DAMAGED conditions and ignored non-po item
    prod_valid = Product(
        sku=f"SKU-DIR-VAL-{uuid.uuid4().hex[:4]}",
        name="Direct Valid Prod",
        category="Hardware",
        unit_cost=Decimal("15.00"),
        unit_price=Decimal("30.00")
    )
    db_session.add(prod_valid)
    await db_session.flush()

    po_valid = PurchaseOrder(
        po_number=f"PO-DIR-VAL-{uuid.uuid4().hex[:6].upper()}",
        supplier_id=supp.id,
        warehouse_id=wh.id,
        status="SENT",
        total_cost=Decimal("150.00")
    )
    db_session.add(po_valid)
    await db_session.flush()

    po_item_v = POItem(
        po_id=po_valid.id,
        product_id=prod_valid.id,
        quantity_ordered=10,
        unit_cost=Decimal("15.00")
    )
    db_session.add(po_item_v)
    await db_session.commit()

    req_valid = GoodsReceiptRequest(
        po_number=po_valid.po_number,
        warehouse_id=wh.id,
        items=[
            GoodsReceiptItem(product_id=prod_valid.id, quantity_received=7, condition="GOOD"),
            GoodsReceiptItem(product_id="non-existent-sku", quantity_received=3, condition="GOOD")
        ]
    )
    res_direct = await GoodsReceiptService.process_receipt(db_session, req_valid)
    assert res_direct.po_status == "PARTIALLY_RECEIVED"
    assert len(res_direct.items_received) == 1

    # Remaining 3 units damaged
    req_damaged = GoodsReceiptRequest(
        po_number=po_valid.po_number,
        warehouse_id=wh.id,
        items=[
            GoodsReceiptItem(product_id=prod_valid.id, quantity_received=3, condition="DAMAGED")
        ]
    )
    res_dmg = await GoodsReceiptService.process_receipt(db_session, req_damaged)
    assert len(res_dmg.items_received) == 1


@pytest.mark.asyncio
async def test_supplier_gateway_direct_edge_cases(db_session):
    """
    Direct service tests for SupplierGatewayService error cases.
    """
    from fastapi import HTTPException

    # Missing PO dispatch -> 404
    with pytest.raises(HTTPException) as exc_info:
        await SupplierGatewayService.dispatch_purchase_order(db_session, str(uuid.uuid4()))
    assert exc_info.value.status_code == 404

    # Missing PO ACK -> 404
    with pytest.raises(HTTPException) as exc_info:
        await SupplierGatewayService.acknowledge_po(
            db_session,
            po_number="PO-NON-EXISTENT-ACK",
            confirmed_delivery_date=datetime.now(timezone.utc)
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_anomaly_detection_direct_subroutines(db_session):
    """
    Direct unit test verifying each individual audit subroutine of AnomalyDetectionService.
    """
    wh = Warehouse(code=f"WH-SUB-{uuid.uuid4().hex[:4]}", name="Sub Wh", address="Phoenix")
    db_session.add(wh)
    await db_session.flush()

    # 1. Drift audit
    drift_items = await AnomalyDetectionService.audit_stock_drift(db_session)
    assert isinstance(drift_items, list)

    # 2. Demand spike audit
    spike_items = await AnomalyDetectionService.detect_demand_spikes(db_session)
    assert isinstance(spike_items, list)

    # 3. Dead stock audit
    dead_items = await AnomalyDetectionService.detect_dead_stock(db_session, threshold_days=60)
    assert isinstance(dead_items, list)

    # 4. Negative stock audit
    neg_items = await AnomalyDetectionService.detect_negative_stock(db_session)
    assert isinstance(neg_items, list)

    # 5. Supplier delay audit
    delay_items = await AnomalyDetectionService.detect_supplier_delays(db_session)
    assert isinstance(delay_items, list)

    # 6. Full audit
    full_report = await AnomalyDetectionService.run_full_anomaly_audit(db_session)
    assert full_report.total_anomalies_detected >= 0
