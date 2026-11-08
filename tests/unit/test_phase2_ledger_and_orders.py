import asyncio
import base64
import hashlib
import hmac
import json
import uuid
import pytest
from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.product import Product
from backend.app.models.warehouse import Warehouse
from backend.app.services.ledger_service import InsufficientStockException, InventoryLedgerService
from backend.app.services.order_service import OrderService


from backend.app.models.user import User


@pytest.fixture
async def auth_headers(db_session):
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"admin_{user_id[:8]}@example.com",
        hashed_password="fakehashedpassword",
        full_name="Admin Test",
        role="admin",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(subject=user.id, role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_event_sourced_ledger_operations(db_session):
    """Verify event-sourced ledger: stock is purely the integral of transactions."""
    prod_id = str(uuid.uuid4())
    wh_id = str(uuid.uuid4())

    # 1. Credit 100 units via RECEIPT
    tx1, stock1 = await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="RECEIPT",
        quantity_delta=100,
        reference_type="PO",
        reference_id="PO-001",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    assert stock1.on_hand == 100
    assert stock1.available == 100
    assert stock1.reserved == 0

    # 2. Debit 30 units via SALE
    tx2, stock2 = await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="SALE",
        quantity_delta=-30,
        reference_type="ORDER",
        reference_id="ORD-001",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    assert stock2.on_hand == 70
    assert stock2.available == 70

    # 3. Debit 5 units via DAMAGE
    tx3, stock3 = await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="DAMAGE",
        quantity_delta=-5,
        reference_type="MANUAL",
        reference_id="AUDIT-1",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    assert stock3.on_hand == 65
    assert stock3.available == 65

    # 4. Reconcile against integral of events
    recon = await InventoryLedgerService.reconcile_stock_levels(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id
    )
    assert recon["cached_on_hand"] == 65
    assert recon["ledger_sum_on_hand"] == 65
    assert recon["discrepancy"] == 0
    assert recon["is_synchronized"] is True


@pytest.mark.asyncio
async def test_negative_stock_prevention(db_session):
    """Verify that ledger rejects transactions that would drive stock below zero."""
    prod_id = str(uuid.uuid4())
    wh_id = str(uuid.uuid4())

    # Initial stock 10
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="RECEIPT",
        quantity_delta=10,
        reference_type="PO",
        reference_id="PO-INIT",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )

    # Attempt to debit 15 units (exceeds 10)
    with pytest.raises(InsufficientStockException):
        await InventoryLedgerService.record_transaction(
            db=db_session,
            product_id=prod_id,
            warehouse_id=wh_id,
            transaction_type="SALE",
            quantity_delta=-15,
            reference_type="ORDER",
            reference_id="ORD-OVER",
            idempotency_key=f"tx_{uuid.uuid4()}"
        )


@pytest.mark.asyncio
async def test_idempotency_deduplication(db_session):
    """Verify that replaying the same idempotency_key returns cached transaction without mutating stock."""
    prod_id = str(uuid.uuid4())
    wh_id = str(uuid.uuid4())
    idem_key = f"idem_test_{uuid.uuid4()}"

    # First write
    tx1, stock1 = await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="RECEIPT",
        quantity_delta=50,
        reference_type="PO",
        reference_id="PO-IDEM",
        idempotency_key=idem_key
    )
    assert stock1.on_hand == 50

    # Second write with exact same idempotency_key
    tx2, stock2 = await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="RECEIPT",
        quantity_delta=50,
        reference_type="PO",
        reference_id="PO-IDEM",
        idempotency_key=idem_key
    )
    assert tx2.id == tx1.id
    assert stock2.on_hand == 50  # Must NOT double to 100!


@pytest.mark.asyncio
async def test_order_reservation_and_fulfillment_lifecycle(async_client, db_session, auth_headers):
    """Test full order lifecycle: reserve -> fulfill -> stock deduction."""
    # 1. Setup Warehouse and Product
    wh = Warehouse(code=f"WH_{uuid.uuid4().hex[:6]}", name="Central Hub", is_active=True)
    prod = Product(
        sku=f"SKU_{uuid.uuid4().hex[:6]}",
        name="Industrial Sensor",
        category="Electronics",
        unit_cost=100.00,
        unit_price=150.00
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # 2. Add 20 units stock via Ledger
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod.id,
        warehouse_id=wh.id,
        transaction_type="RECEIPT",
        quantity_delta=20,
        reference_type="PO",
        reference_id="PO-LIFECYCLE",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    await db_session.commit()

    # 3. Place Order for 5 units
    order_payload = {
        "order_number": f"ORD_{uuid.uuid4().hex[:8]}",
        "warehouse_id": wh.id,
        "items": [
            {"product_id": prod.id, "quantity": 5, "unit_price": "150.00"}
        ],
        "idempotency_key": f"idem_ord_{uuid.uuid4()}"
    }
    ord_resp = await async_client.post("/api/v1/orders/", json=order_payload, headers=auth_headers)
    assert ord_resp.status_code == 201
    ord_data = ord_resp.json()
    assert ord_data["status"] == "RESERVED"
    order_id = ord_data["id"]

    # Verify stock levels: on_hand=20, reserved=5, available=15
    stock_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert stock_resp.status_code == 200
    stock_data = stock_resp.json()[0]
    assert stock_data["on_hand"] == 20
    assert stock_data["reserved"] == 5
    assert stock_data["available"] == 15

    # 4. Fulfill Order
    fulfill_resp = await async_client.post(f"/api/v1/orders/{order_id}/fulfill", headers=auth_headers)
    assert fulfill_resp.status_code == 200
    assert fulfill_resp.json()["status"] == "FULFILLED"

    # Verify stock levels after fulfillment: on_hand=15, reserved=0, available=15
    stock_resp2 = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    stock_data2 = stock_resp2.json()[0]
    assert stock_data2["on_hand"] == 15
    assert stock_data2["reserved"] == 0
    assert stock_data2["available"] == 15


@pytest.mark.asyncio
async def test_order_cancellation_releases_reserved_stock(async_client, db_session, auth_headers):
    """Test that cancelling an order releases reserved stock back to available pool."""
    wh = Warehouse(code=f"WH_{uuid.uuid4().hex[:6]}", name="Cancel Hub", is_active=True)
    prod = Product(
        sku=f"SKU_{uuid.uuid4().hex[:6]}",
        name="Smart Widget",
        category="Gadgets",
        unit_cost=50.00,
        unit_price=80.00
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # 10 units stock
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod.id,
        warehouse_id=wh.id,
        transaction_type="RECEIPT",
        quantity_delta=10,
        reference_type="PO",
        reference_id="PO-CANCEL-TEST",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    await db_session.commit()

    # Reserve 4 units
    order_payload = {
        "order_number": f"ORD_{uuid.uuid4().hex[:8]}",
        "warehouse_id": wh.id,
        "items": [{"product_id": prod.id, "quantity": 4, "unit_price": "80.00"}],
        "idempotency_key": f"idem_cancel_{uuid.uuid4()}"
    }
    ord_resp = await async_client.post("/api/v1/orders/", json=order_payload, headers=auth_headers)
    order_id = ord_resp.json()["id"]

    # Cancel order
    cancel_resp = await async_client.post(f"/api/v1/orders/{order_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Stock should be fully available again: on_hand=10, reserved=0, available=10
    stock_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    stock_data = stock_resp.json()[0]
    assert stock_data["on_hand"] == 10
    assert stock_data["reserved"] == 0
    assert stock_data["available"] == 10


@pytest.mark.asyncio
async def test_shopify_webhook_signature_verification(async_client, db_session):
    """Test Shopify HMAC signature validation on webhook endpoint."""
    wh = Warehouse(code="DEFAULT_WH", name="Default Webhook Warehouse", is_active=True)
    sku = f"SHOPIFY_SKU_{uuid.uuid4().hex[:6]}"
    prod = Product(
        sku=sku,
        name="Shopify Test Item",
        category="Online",
        unit_cost=10.00,
        unit_price=25.00
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # Add 50 units
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod.id,
        warehouse_id=wh.id,
        transaction_type="RECEIPT",
        quantity_delta=50,
        reference_type="PO",
        reference_id="PO-SHOPIFY",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    await db_session.commit()

    webhook_payload = {
        "id": 99887766,
        "name": "#1001",
        "total_price": "50.00",
        "line_items": [
            {
                "id": 112233,
                "sku": sku,
                "quantity": 2,
                "price": "25.00"
            }
        ]
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")

    # Compute valid HMAC
    secret = settings.SHOPIFY_WEBHOOK_SECRET.encode("utf-8")
    computed_digest = hmac.new(secret, raw_body, hashlib.sha256).digest()
    valid_hmac = base64.b64encode(computed_digest).decode("utf-8")

    # 1. Test with valid HMAC -> 201 Created
    headers = {"X-Shopify-Hmac-Sha256": valid_hmac, "Content-Type": "application/json"}
    resp = await async_client.post(
        f"/api/v1/orders/webhook/shopify?warehouse_id={wh.id}",
        content=raw_body,
        headers=headers
    )
    assert resp.status_code == 201
    assert resp.json()["channel"] == "SHOPIFY_WEBHOOK"

    # 2. Test with invalid HMAC -> 401 Unauthorized
    bad_headers = {"X-Shopify-Hmac-Sha256": "invalid_fake_hmac", "Content-Type": "application/json"}
    bad_resp = await async_client.post(
        f"/api/v1/orders/webhook/shopify?warehouse_id={wh.id}",
        content=raw_body,
        headers=bad_headers
    )
    assert bad_resp.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_orders_race_condition(async_client, db_session, auth_headers):
    """
    Concurrency Stress Test:
    Simulate multiple simultaneous requests attempting to reserve the last remaining stock.
    Stock: 10 units.
    5 concurrent requests of 3 units each (Total demand: 15 units).
    Expected: Exactly 3 succeed (9 units reserved), 2 fail (oversell prevented).
    """
    wh = Warehouse(code=f"WH_CONC_{uuid.uuid4().hex[:6]}", name="Race Test Warehouse", is_active=True)
    prod = Product(
        sku=f"SKU_CONC_{uuid.uuid4().hex[:6]}",
        name="High Demand Item",
        category="FlashSale",
        unit_cost=20.00,
        unit_price=35.00
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # Seed exactly 10 units
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod.id,
        warehouse_id=wh.id,
        transaction_type="RECEIPT",
        quantity_delta=10,
        reference_type="PO",
        reference_id="PO-CONC",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    await db_session.commit()

    async def place_order(idx: int):
        payload = {
            "order_number": f"ORD_RACE_{idx}_{uuid.uuid4().hex[:6]}",
            "warehouse_id": wh.id,
            "items": [{"product_id": prod.id, "quantity": 3, "unit_price": "35.00"}],
            "idempotency_key": f"idem_race_{idx}_{uuid.uuid4()}"
        }
        return await async_client.post("/api/v1/orders/", json=payload, headers=auth_headers)

    # Fire 5 concurrent requests
    responses = await asyncio.gather(*(place_order(i) for i in range(5)))

    status_codes = [r.status_code for r in responses]
    success_count = status_codes.count(201)
    failure_count = status_codes.count(400)

    # 3 * 3 = 9 units <= 10. The 4th order would require 12 units > 10, so it must fail.
    assert success_count == 3, f"Expected 3 orders to succeed, but got {success_count}. Statuses: {status_codes}"
    assert failure_count == 2, f"Expected 2 orders to fail with insufficient stock, but got {failure_count}."

    # Verify final stock level in database
    stock_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    stock_data = stock_resp.json()[0]
    assert stock_data["on_hand"] == 10
    assert stock_data["reserved"] == 9
    assert stock_data["available"] == 1


@pytest.mark.asyncio
async def test_manual_adjustment_and_reconciliation_auto_correct(async_client, db_session, auth_headers):
    """Test manual adjustment endpoint and reconciliation auto-correction."""
    wh = Warehouse(code=f"WH_{uuid.uuid4().hex[:6]}", name="Adj Hub", is_active=True)
    prod = Product(
        sku=f"SKU_{uuid.uuid4().hex[:6]}",
        name="Adjustment Target Item",
        category="Hardware",
        unit_cost=15.00,
        unit_price=30.00
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # 1. Post manual adjustment of +25 units
    adj_payload = {
        "product_id": prod.id,
        "warehouse_id": wh.id,
        "quantity_delta": 25,
        "adjustment_type": "ADJUSTMENT",
        "reason": "Physical count found surplus stock",
        "idempotency_key": f"adj_{uuid.uuid4()}"
    }
    adj_resp = await async_client.post("/api/v1/ledger/adjustment", json=adj_payload, headers=auth_headers)
    assert adj_resp.status_code == 201
    assert adj_resp.json()["quantity_delta"] == 25

    # 2. Simulate artificial cache drift (corrupt stock_levels directly)
    stock = await InventoryLedgerService.get_or_create_stock_level(db_session, prod.id, wh.id, for_update=True)
    stock.on_hand = 999  # Artificially corrupted
    await db_session.commit()

    # 3. Call reconcile with auto_correct=True
    recon_resp = await async_client.post(
        f"/api/v1/ledger/reconcile?product_id={prod.id}&warehouse_id={wh.id}&auto_correct=true",
        headers=auth_headers
    )
    assert recon_resp.status_code == 200
    recon_data = recon_resp.json()
    assert recon_data["is_synchronized"] is False
    assert recon_data["ledger_sum_on_hand"] == 25
    assert recon_data["cached_on_hand"] == 999

    # Verify that stock_level has been corrected back to 25 via API
    stock_resp = await async_client.get(
        f"/api/v1/ledger/stock-levels?product_id={prod.id}&warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert stock_resp.status_code == 200
    assert stock_resp.json()[0]["on_hand"] == 25


@pytest.mark.asyncio
async def test_order_and_transaction_query_endpoints(async_client, db_session, auth_headers):
    """Test GET /ledger/transactions and GET /orders endpoints."""
    # Query transactions
    tx_resp = await async_client.get("/api/v1/ledger/transactions?limit=10", headers=auth_headers)
    assert tx_resp.status_code == 200
    assert isinstance(tx_resp.json(), list)

    # Query orders list
    ord_resp = await async_client.get("/api/v1/orders/?limit=10", headers=auth_headers)
    assert ord_resp.status_code == 200
    orders_list = ord_resp.json()
    assert isinstance(orders_list, list)

    if orders_list:
        first_order = orders_list[0]
        single_resp = await async_client.get(f"/api/v1/orders/{first_order['id']}", headers=auth_headers)
        assert single_resp.status_code == 200
        assert single_resp.json()["id"] == first_order["id"]


@pytest.mark.asyncio
async def test_ledger_service_edge_cases(db_session):
    """Test ledger edge cases: negative quantities, direct release, and direct fulfillment."""
    prod_id = str(uuid.uuid4())
    wh_id = str(uuid.uuid4())

    # Initial stock: 10 units
    await InventoryLedgerService.record_transaction(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        transaction_type="RECEIPT",
        quantity_delta=10,
        reference_type="PO",
        reference_id="PO-EDGE",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )

    # 1. Invalid reservation quantity <= 0
    with pytest.raises(ValueError, match="strictly positive"):
        await InventoryLedgerService.reserve_stock(
            db=db_session,
            product_id=prod_id,
            warehouse_id=wh_id,
            quantity=0,
            reference_id="REF-0",
            idempotency_key=f"tx_{uuid.uuid4()}"
        )

    # 2. Reserve 5 units
    stock = await InventoryLedgerService.reserve_stock(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        quantity=5,
        reference_id="REF-5",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    assert stock.reserved == 5
    assert stock.available == 5

    # 3. Direct release of 2 units
    stock_rel = await InventoryLedgerService.release_reserved_stock(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        quantity=2,
        reference_id="REF-REL"
    )
    assert stock_rel.reserved == 3
    assert stock_rel.available == 7

    # 4. Direct fulfillment of remaining 3 reserved units
    tx, stock_ful = await InventoryLedgerService.fulfill_reserved_stock(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        quantity=3,
        reference_id="REF-FUL",
        idempotency_key=f"tx_ful_{uuid.uuid4()}"
    )
    assert stock_ful.on_hand == 7
    assert stock_ful.reserved == 0
    assert stock_ful.available == 7
    assert tx.transaction_type == "SALE"

    # 5. Test attempting transaction that drives available negative
    # on_hand is 7. Reserve 5 units -> available is 2. Attempt SALE of -5 -> fails.
    await InventoryLedgerService.reserve_stock(
        db=db_session,
        product_id=prod_id,
        warehouse_id=wh_id,
        quantity=5,
        reference_id="REF-RES-FAIL",
        idempotency_key=f"tx_{uuid.uuid4()}"
    )
    with pytest.raises(InsufficientStockException):
        await InventoryLedgerService.record_transaction(
            db=db_session,
            product_id=prod_id,
            warehouse_id=wh_id,
            transaction_type="DAMAGE",
            quantity_delta=-5,
            reference_type="AUDIT",
            reference_id="REF-DMG",
            idempotency_key=f"tx_{uuid.uuid4()}"
        )
