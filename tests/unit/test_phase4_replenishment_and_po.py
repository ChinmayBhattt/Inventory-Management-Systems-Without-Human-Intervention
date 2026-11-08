from datetime import datetime
import math
import os
import uuid
from decimal import Decimal
import pytest
from backend.app.core.security import create_access_token
from backend.app.models.alert import Alert
from backend.app.models.product import Product
from backend.app.models.purchase_order import PurchaseOrder
from backend.app.models.reorder_policy import ReorderPolicy
from backend.app.models.supplier import Supplier
from backend.app.models.user import User
from backend.app.models.warehouse import Warehouse
from backend.app.services.ledger_service import InventoryLedgerService
from backend.app.services.po_pdf_generator import PurchaseOrderPDFGenerator
from backend.app.services.replenishment_math import (
    calculate_economic_order_quantity,
    calculate_reorder_point,
    calculate_safety_stock,
    evaluate_replenishment_trigger,
)


@pytest.fixture
async def auth_headers(db_session):
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"procurement_{user_id[:8]}@example.com",
        hashed_password="hash",
        full_name="Procurement Manager",
        role="admin",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(subject=user.id, role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_replenishment_mathematics_exact_formulas():
    """Verify exact analytical formulas for Safety Stock, ROP, and EOQ."""
    # 1. Safety Stock: Z=1.65 (95% service), sigma=4.0, lead_time=9 days
    # SS = 1.65 * 4.0 * sqrt(9) = 1.65 * 4 * 3 = 19.8 -> ceil(19.8) = 20
    ss = calculate_safety_stock(service_level_z=1.65, sigma_demand=4.0, lead_time_days=9)
    assert ss == 20

    # 2. Reorder Point: avg_daily_demand=10, lead_time=9, safety_stock=20
    # ROP = (10 * 9) + 20 = 90 + 20 = 110
    rop = calculate_reorder_point(avg_daily_demand=10.0, lead_time_days=9, safety_stock=ss)
    assert rop == 110

    # 3. Economic Order Quantity:
    # D = 3650 units/yr, S = $50/order, Unit Cost = $20, Holding % = 20% (0.20)
    # H = 0.20 * 20 = $4/unit/yr
    # EOQ = sqrt((2 * 3650 * 50) / 4) = sqrt(365000 / 4) = sqrt(91250) = 302.076 -> round = 302
    eoq = calculate_economic_order_quantity(
        annual_demand=3650.0,
        fixed_order_cost=50.0,
        unit_cost=20.0,
        holding_cost_annual_pct=0.20
    )
    assert eoq == 302


def test_replenishment_math_edge_cases():
    """Verify math stability across boundary conditions (zeroes, negative inputs)."""
    # Zero lead time
    assert calculate_safety_stock(service_level_z=1.65, sigma_demand=5.0, lead_time_days=0) == 0

    # Zero daily demand
    assert calculate_reorder_point(avg_daily_demand=0.0, lead_time_days=7, safety_stock=10) == 10

    # Zero holding cost or zero demand in EOQ returns safe fallback 1
    assert calculate_economic_order_quantity(0.0, 50.0, 20.0, 0.2) == 1
    assert calculate_economic_order_quantity(1000.0, 50.0, 20.0, 0.0) == 1

    # Trigger evaluation:
    # On hand 120, on order 0, reserved 0 -> Effective 120 > ROP 110 -> False
    trig, eff, qty = evaluate_replenishment_trigger(120, 0, 0, 110, 50)
    assert trig is False
    assert eff == 120
    assert qty == 0

    # On hand 50, on order 20, reserved 10 -> Effective 60 <= ROP 110 -> True
    # Deficit = 110 - 60 = 50. EOQ = 75. Recommended = max(75, 50) = 75
    trig2, eff2, qty2 = evaluate_replenishment_trigger(50, 20, 10, 110, 75)
    assert trig2 is True
    assert eff2 == 60
    assert qty2 == 75


def test_reportlab_pdf_generation_direct():
    """Verify vector PDF document is generated on disk with valid PDF structure."""
    po_num = f"PO-TEST-{uuid.uuid4().hex[:6].upper()}"
    items = [
        {"sku": "SKU-TEST-1", "name": "Precision Motor", "quantity_ordered": 25, "unit_cost": 45.00},
        {"sku": "SKU-TEST-2", "name": "Control Board", "quantity_ordered": 10, "unit_cost": 120.00},
    ]
    total = Decimal("2325.00")

    pdf_path = PurchaseOrderPDFGenerator.generate_pdf(
        po_number=po_num,
        supplier_name="Global Tech Logistics",
        supplier_email="sales@globaltech.example.com",
        warehouse_name="Distribution Center North",
        warehouse_code="WH-NORTH",
        created_at=datetime.now(),
        expected_delivery=datetime.now(),
        items=items,
        total_cost=total,
        status="AUTO_APPROVED",
        approval_mode="AUTONOMOUS"
    )

    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000  # Non-trivial PDF file

    # Read binary header
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


@pytest.mark.asyncio
async def test_autonomous_replenishment_auto_approval_and_review_flow(async_client, db_session, auth_headers):
    """
    Test End-to-End Replenishment:
    1. Low-cost order within limit -> AUTO_APPROVED, increments on_order, generates PDF.
    2. Expensive order exceeding limit -> NEEDS_REVIEW, generates Alert, manager manual approval.
    """
    wh = Warehouse(code=f"WH_{uuid.uuid4().hex[:6]}", name="Auto WH", is_active=True)
    supp = Supplier(
        name="Reliable Vendor Co",
        email="orders@reliable.example.com",
        lead_time_days=5,
        reliability_score=0.95
    )
    db_session.add(wh)
    db_session.add(supp)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(supp)

    # 1. Product A: cheap ($10 unit cost), limit $5,000 -> Will AUTO_APPROVE
    prod_a = Product(
        sku=f"SKU_CHEAP_{uuid.uuid4().hex[:6]}",
        name="Cheap Resistor",
        category="Components",
        unit_cost=Decimal("10.00"),
        unit_price=Decimal("15.00"),
        default_supplier_id=supp.id
    )
    # 2. Product B: expensive ($2,000 unit cost), limit $1,000 -> Will require review
    prod_b = Product(
        sku=f"SKU_EXP_{uuid.uuid4().hex[:6]}",
        name="Expensive Turbine",
        category="HeavyMachinery",
        unit_cost=Decimal("2000.00"),
        unit_price=Decimal("3500.00"),
        default_supplier_id=supp.id
    )
    db_session.add(prod_a)
    db_session.add(prod_b)
    await db_session.commit()
    await db_session.refresh(prod_a)
    await db_session.refresh(prod_b)

    # Set initial stock: 0 on hand -> both trigger replenishment
    await InventoryLedgerService.get_or_create_stock_level(db_session, prod_a.id, wh.id, for_update=True)
    await InventoryLedgerService.get_or_create_stock_level(db_session, prod_b.id, wh.id, for_update=True)
    await db_session.commit()

    # Create policy for Product B with low limit ($1,000)
    policy_b = ReorderPolicy(
        product_id=prod_b.id,
        warehouse_id=wh.id,
        service_level_z=1.65,
        lead_time_days=7,
        holding_cost_annual_pct=0.20,
        fixed_order_cost=Decimal("50.00"),
        safety_stock=2,
        reorder_point=5,
        economic_order_quantity=5,
        auto_approve_max_po_value=Decimal("1000.00"),  # $1,000 ceiling!
        is_autonomous=True
    )
    db_session.add(policy_b)
    await db_session.commit()

    # Execute evaluation for Product A
    eval_a_resp = await async_client.post(
        f"/api/v1/replenishment/evaluate/{prod_a.id}?warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert eval_a_resp.status_code == 200
    res_a = eval_a_resp.json()
    assert res_a["is_triggered"] is True
    assert res_a["po_status"] == "AUTO_APPROVED"
    assert res_a["on_order"] > 0  # Automatically credited to on_order!

    # Execute evaluation for Product B
    eval_b_resp = await async_client.post(
        f"/api/v1/replenishment/evaluate/{prod_b.id}?warehouse_id={wh.id}",
        headers=auth_headers
    )
    assert eval_b_resp.status_code == 200
    res_b = eval_b_resp.json()
    assert res_b["is_triggered"] is True
    assert res_b["po_status"] == "NEEDS_REVIEW"
    po_b_number = res_b["po_number"]

    # Verify PO B in database
    po_list_resp = await async_client.get(
        f"/api/v1/purchase-orders/?status=NEEDS_REVIEW",
        headers=auth_headers
    )
    assert po_list_resp.status_code == 200
    pos = po_list_resp.json()
    po_b = next((p for p in pos if p["po_number"] == po_b_number), None)
    assert po_b is not None
    assert po_b["approval_mode"] == "MANUAL"

    # Human manager manually approves PO B
    approve_resp = await async_client.post(
        f"/api/v1/purchase-orders/{po_b['id']}/approve",
        json={"notes": "Special override approved by director."},
        headers=auth_headers
    )
    assert approve_resp.status_code == 200
    approved_data = approve_resp.json()
    assert approved_data["status"] == "AUTO_APPROVED"

    # Verify PDF download endpoint
    pdf_resp = await async_client.get(
        f"/api/v1/purchase-orders/{po_b['id']}/pdf",
        headers=auth_headers
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 500


@pytest.mark.asyncio
async def test_replenishment_sweep_and_policy_crud_endpoints(async_client, db_session, auth_headers):
    """Test full replenishment sweep, policy listing, policy updating, and PO cancellation."""
    wh = Warehouse(code=f"WH_{uuid.uuid4().hex[:6]}", name="Sweep WH", is_active=True)
    prod = Product(
        sku=f"SKU_SWEEP_{uuid.uuid4().hex[:6]}",
        name="Sweep Item",
        category="Tools",
        unit_cost=Decimal("25.00"),
        unit_price=Decimal("40.00")
    )
    db_session.add(wh)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(wh)
    await db_session.refresh(prod)

    # 1. Full Replenishment Sweep
    sweep_resp = await async_client.post("/api/v1/replenishment/evaluate", headers=auth_headers)
    assert sweep_resp.status_code == 200
    sweep_data = sweep_resp.json()
    assert sweep_data["evaluated_skus"] >= 1
    assert "total_spend_committed" in sweep_data

    # 2. List Policies
    pol_resp = await async_client.get(f"/api/v1/replenishment/policies?product_id={prod.id}", headers=auth_headers)
    assert pol_resp.status_code == 200
    policies = pol_resp.json()
    assert len(policies) >= 1
    policy_id = policies[0]["id"]

    # 3. Update Policy Settings
    update_payload = {
        "service_level_z": 2.33,  # 99% service level
        "auto_approve_max_po_value": "10000.00",
        "fixed_order_cost": "75.00"
    }
    put_resp = await async_client.put(
        f"/api/v1/replenishment/policies/{policy_id}",
        json=update_payload,
        headers=auth_headers
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["service_level_z"] == 2.33
    assert float(updated["auto_approve_max_po_value"]) == 10000.0

    # 4. Cancel PO
    # Get any active PO and cancel it
    po_resp = await async_client.get("/api/v1/purchase-orders/?limit=1", headers=auth_headers)
    if po_resp.json():
        po_to_cancel = po_resp.json()[0]
        cancel_resp = await async_client.post(
            f"/api/v1/purchase-orders/{po_to_cancel['id']}/cancel",
            headers=auth_headers
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "CANCELLED"
