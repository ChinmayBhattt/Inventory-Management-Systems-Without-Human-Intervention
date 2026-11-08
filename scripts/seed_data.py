import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
import os
import random
import uuid
from typing import List, Tuple

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("ENVIRONMENT", "development")

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.logging import logger
from backend.app.core.security import get_password_hash
from backend.app.models.alert import Alert
from backend.app.models.inventory_transaction import InventoryTransaction
from backend.app.models.order import Order, OrderItem
from backend.app.models.product import Product
from backend.app.models.purchase_order import POItem, PurchaseOrder
from backend.app.models.reorder_policy import ReorderPolicy
from backend.app.models.stock_level import StockLevel
from backend.app.models.supplier import Supplier
from backend.app.models.user import User
from backend.app.models.warehouse import Warehouse
from backend.app.services.po_pdf_generator import PurchaseOrderPDFGenerator
from backend.app.services.replenishment_math import (
    calculate_economic_order_quantity,
    calculate_reorder_point,
    calculate_safety_stock,
)


CATEGORIES_AND_SKUS = [
    # Electronics (18 SKUs)
    ("ELEC-IPHONE15", "Pro Smartphone 256GB Titanium", "Electronics", Decimal("799.00"), Decimal("1099.00"), 4.0),
    ("ELEC-MACBOOK14", "14-inch Aluminum Laptop M3", "Electronics", Decimal("1250.00"), Decimal("1799.00"), 2.5),
    ("ELEC-AIRPODS", "Active Noise-Canceling Earbuds Pro", "Electronics", Decimal("140.00"), Decimal("249.00"), 8.0),
    ("ELEC-SONYWH", "Premium Over-Ear Wireless Headphones", "Electronics", Decimal("210.00"), Decimal("349.00"), 3.5),
    ("ELEC-USBC-2M", "Braided 240W USB-C Fast Cable 2M", "Electronics", Decimal("6.50"), Decimal("19.99"), 25.0),
    ("ELEC-CHARGER-65W", "GaN 65W Dual-Port Wall Charger", "Electronics", Decimal("14.00"), Decimal("39.99"), 15.0),
    ("ELEC-LOGI-MX", "Ergonomic Bluetooth Wireless Mouse", "Electronics", Decimal("45.00"), Decimal("99.99"), 10.0),
    ("ELEC-MECH-KB", "RGB Mechanical Keyboard Cherry Brown", "Electronics", Decimal("65.00"), Decimal("139.99"), 6.0),
    ("ELEC-DELL-4K", "27-inch 4K IPS Ultra-Sharp Monitor", "Electronics", Decimal("280.00"), Decimal("449.00"), 3.0),
    ("ELEC-SAMSUNG-SSD", "2TB NVMe PCIe 4.0 Solid State Drive", "Electronics", Decimal("95.00"), Decimal("169.99"), 7.0),
    ("ELEC-ANKER-PB", "20,000mAh Ultra-Compact Power Bank", "Electronics", Decimal("24.00"), Decimal("59.99"), 12.0),
    ("ELEC-WEBCAM-4K", "Ultra-HD 4K Streaming HDR Webcam", "Electronics", Decimal("55.00"), Decimal("119.99"), 5.0),
    ("ELEC-DOCK-TB4", "Thunderbolt 4 Quad-Display Dock", "Electronics", Decimal("130.00"), Decimal("249.00"), 2.0),
    ("ELEC-SMARTWATCH", "GPS Fitness Waterproof Smartwatch", "Electronics", Decimal("110.00"), Decimal("219.00"), 4.5),
    ("ELEC-PAD-STAND", "Adjustable Aluminum Ergonomic Stand", "Electronics", Decimal("12.00"), Decimal("29.99"), 11.0),
    ("ELEC-MIC-USB", "Studio Cardioid Condenser USB Mic", "Electronics", Decimal("48.00"), Decimal("99.99"), 4.0),
    ("ELEC-SPEAKER-BT", "Rugged Waterproof Bluetooth Speaker", "Electronics", Decimal("38.00"), Decimal("79.99"), 7.5),
    ("ELEC-ROUTER-WIFI6", "Tri-Band Wi-Fi 6 Mesh System", "Electronics", Decimal("115.00"), Decimal("199.99"), 3.5),

    # Apparel (16 SKUs)
    ("APP-TEE-BLK-M", "Heavyweight Cotton Crewneck T-Shirt (Black, M)", "Apparel", Decimal("10.00"), Decimal("28.00"), 20.0),
    ("APP-TEE-WHT-L", "Heavyweight Cotton Crewneck T-Shirt (White, L)", "Apparel", Decimal("10.00"), Decimal("28.00"), 22.0),
    ("APP-HOODIE-GRY", "French Terry Zip-Up Hoodie (Heather Grey)", "Apparel", Decimal("28.00"), Decimal("68.00"), 12.0),
    ("APP-JEANS-SLIM", "Selvedge Stretch Denim Jeans Slim Fit", "Apparel", Decimal("35.00"), Decimal("88.00"), 8.0),
    ("APP-CHINO-NVY", "All-Day Stretch Cotton Chinos (Navy)", "Apparel", Decimal("25.00"), Decimal("64.00"), 9.0),
    ("APP-SHOE-RUN", "Breathable Cushion Running Trainers", "Apparel", Decimal("45.00"), Decimal("115.00"), 11.0),
    ("APP-SHOE-BOOT", "Waterproof Weatherproof Chelsea Boots", "Apparel", Decimal("65.00"), Decimal("160.00"), 4.0),
    ("APP-JACKET-RAIN", "Packable Technical Windproof Rain Shell", "Apparel", Decimal("40.00"), Decimal("95.00"), 5.5),
    ("APP-SOCKS-WOOL", "Merino Wool Trail Hiking Socks 3-Pack", "Apparel", Decimal("9.00"), Decimal("24.00"), 18.0),
    ("APP-BEANI-KNT", "Ribbed Cashmere-Wool Blend Beanie", "Apparel", Decimal("12.00"), Decimal("32.00"), 14.0),
    ("APP-BELT-LTHR", "Full Grain Italian Burnished Leather Belt", "Apparel", Decimal("18.00"), Decimal("48.00"), 6.5),
    ("APP-GLOVES-THRM", "Touchscreen Insulated Winter Gloves", "Apparel", Decimal("8.00"), Decimal("22.00"), 10.0),
    ("APP-CAP-ATHL", "Moisture-Wicking Performance Sport Cap", "Apparel", Decimal("9.50"), Decimal("26.00"), 12.0),
    ("APP-SHORTS-GYM", "Quick-Dry Lined Training Athletic Shorts", "Apparel", Decimal("14.00"), Decimal("38.00"), 15.0),
    ("APP-SWEATER-CRW", "Heritage Lambswool Cable Knit Crewneck", "Apparel", Decimal("34.00"), Decimal("85.00"), 5.0),
    ("APP-BAG-DUFFLE", "Water-Resistant Weekend Travel Duffel", "Apparel", Decimal("32.00"), Decimal("78.00"), 4.5),

    # Groceries (16 SKUs)
    ("GROC-COFFEE-ETH", "Single-Origin Yirgacheffe Whole Beans 1kg", "Groceries", Decimal("12.50"), Decimal("24.99"), 14.0),
    ("GROC-COFFEE-COL", "Colombian Supremo Dark Roast Beans 1kg", "Groceries", Decimal("11.00"), Decimal("22.50"), 16.0),
    ("GROC-TEA-MATCHA", "Ceremonial Uji Japanese Green Matcha 100g", "Groceries", Decimal("14.00"), Decimal("29.99"), 8.0),
    ("GROC-TEA-EARL", "Organic Bergamot Earl Grey Loose Leaf 250g", "Groceries", Decimal("6.50"), Decimal("14.99"), 12.0),
    ("GROC-OATS-ROLLED", "Organic Thick Rolled Gluten-Free Oats 1.5kg", "Groceries", Decimal("4.00"), Decimal("9.49"), 22.0),
    ("GROC-OLIVEOIL-EV", "First Cold Pressed Extra Virgin Olive Oil 750ml", "Groceries", Decimal("9.00"), Decimal("19.99"), 15.0),
    ("GROC-HONEY-RAW", "Raw Unfiltered Wildflower Honey Jar 500g", "Groceries", Decimal("7.00"), Decimal("15.99"), 10.0),
    ("GROC-MILK-OAT", "Barista Blend Creamy Oat Milk 1L (Case of 6)", "Groceries", Decimal("10.50"), Decimal("21.99"), 18.0),
    ("GROC-MILK-ALMD", "Unsweetened Organic Vanilla Almond Milk 1L", "Groceries", Decimal("2.20"), Decimal("4.99"), 24.0),
    ("GROC-CHOC-DARK", "85% Cocoa Single-Estate Dark Chocolate Bar", "Groceries", Decimal("2.40"), Decimal("5.49"), 30.0),
    ("GROC-SALT-HIMAL", "Fine Pure Pink Himalayan Mineral Salt 1kg", "Groceries", Decimal("3.00"), Decimal("7.49"), 16.0),
    ("GROC-PB-CRUNCH", "All-Natural Crunchy Dark Roast Peanut Butter 500g", "Groceries", Decimal("3.20"), Decimal("6.99"), 20.0),
    ("GROC-ALMONDS-RST", "Dry Roasted Lightly Salted California Almonds 500g", "Groceries", Decimal("6.50"), Decimal("13.99"), 13.0),
    ("GROC-QUINOA-ORG", "Pre-Washed Organic Royal White Quinoa 1kg", "Groceries", Decimal("4.50"), Decimal("10.99"), 11.0),
    ("GROC-SYRUP-MAPLE", "Grade A Amber Rich Pure Maple Syrup 500ml", "Groceries", Decimal("8.00"), Decimal("16.99"), 9.0),
    ("GROC-CHIA-SEEDS", "Organic Nutrient-Dense Black Chia Seeds 500g", "Groceries", Decimal("3.80"), Decimal("8.99"), 14.0),
]


def generate_daily_sales_series(base_daily_demand: float, days: int = 365) -> List[int]:
    """
    Generates 365 days of realistic sales with:
    - Linear trend: +15% annual growth
    - Weekly cycle: weekends (Sat/Sun) +40-60%
    - Holiday spikes: Black Friday (3.5x), Holiday (2.5x), Summer (1.8x)
    - Stochastic noise: Poisson variance
    """
    sales = []
    # Day 0 is 365 days ago, Day 364 is yesterday
    for t in range(days):
        # 1. Growth trend: 1.0 -> 1.15
        trend_factor = 1.0 + 0.15 * (t / float(days))

        # 2. Day-of-week multiplier
        # Let t=0 be Monday (weekday 0)
        weekday = t % 7
        dow_mult = {
            0: 0.90,  # Monday
            1: 0.95,  # Tuesday
            2: 1.00,  # Wednesday
            3: 1.05,  # Thursday
            4: 1.30,  # Friday
            5: 1.60,  # Saturday
            6: 1.45,  # Sunday
        }[weekday]

        # 3. Holiday and promotional seasonality
        # Day ~325: Black Friday / Cyber Monday (3.5x)
        # Day ~345-355: Holiday Season (2.5x)
        # Day ~180: Mid-year Summer Promo (1.8x)
        season_mult = 1.0
        if 320 <= t <= 328:
            season_mult = 3.8
        elif 345 <= t <= 356:
            season_mult = 2.4
        elif 175 <= t <= 185:
            season_mult = 1.8
        elif random.random() < 0.02:
            season_mult = random.uniform(1.5, 2.2)  # Occasional flash sale

        expected_demand = base_daily_demand * trend_factor * dow_mult * season_mult

        # 4. Stochastic Poisson/Gaussian noise
        daily_qty = max(0, int(np.random.poisson(lam=expected_demand)))
        sales.append(daily_qty)

    return sales


async def seed_database(clear_existing: bool = True):
    """Orchestrates comprehensive 12-month synthetic database seeding."""
    logger.info("Initializing Database Seeder...")
    random.seed(42)
    np.random.seed(42)

    async with AsyncSessionLocal() as db:
        if clear_existing:
            logger.info("Cleaning existing operational database tables...")
            await db.execute(delete(Alert))
            await db.execute(delete(OrderItem))
            await db.execute(delete(Order))
            await db.execute(delete(POItem))
            await db.execute(delete(PurchaseOrder))
            await db.execute(delete(InventoryTransaction))
            await db.execute(delete(StockLevel))
            await db.execute(delete(ReorderPolicy))
            await db.execute(delete(Product))
            await db.execute(delete(Warehouse))
            await db.execute(delete(Supplier))
            await db.execute(delete(User))
            await db.commit()

        # 1. Seed Users
        logger.info("Seeding Admin and Viewer Users...")
        admin = User(
            id=str(uuid.uuid4()),
            email="admin@example.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Autonomous Procurement Manager",
            role="admin",
            is_active=True
        )
        viewer = User(
            id=str(uuid.uuid4()),
            email="viewer@example.com",
            hashed_password=get_password_hash("viewer123"),
            full_name="Operations Auditor",
            role="viewer",
            is_active=True
        )
        db.add_all([admin, viewer])

        # 2. Seed Warehouses
        logger.info("Seeding Warehouses...")
        wh_chi = Warehouse(code="WH-CHI", name="Central Distribution Hub", address="1000 S Michigan Ave, Chicago, IL")
        wh_nyc = Warehouse(code="WH-NYC", name="East Coast Logistics Center", address="450 W 33rd St, New York, NY")
        wh_lax = Warehouse(code="WH-LAX", name="West Coast Fulfillment Facility", address="2000 World Way, Los Angeles, CA")
        warehouses = [wh_chi, wh_nyc, wh_lax]
        db.add_all(warehouses)
        await db.flush()

        # 3. Seed Suppliers
        logger.info("Seeding Suppliers...")
        supp_elec1 = Supplier(
            name="Apex Global Electronics",
            email="sales@apex-electronics.com",
            api_endpoint="https://api.apex-electronics.com/v1/orders",
            lead_time_days=10,
            minimum_order_value=Decimal("500.00"),
            reliability_score=0.96
        )
        supp_elec2 = Supplier(
            name="Silicon Components Direct",
            email="orders@siliconcomponents.com",
            api_endpoint="https://api.siliconcomponents.com/orders",
            lead_time_days=7,
            minimum_order_value=Decimal("300.00"),
            reliability_score=0.93
        )
        supp_app1 = Supplier(
            name="Premier Garment Mills",
            email="orders@premiergarments.com",
            lead_time_days=14,
            minimum_order_value=Decimal("400.00"),
            reliability_score=0.91
        )
        supp_app2 = Supplier(
            name="Highland Apparel Ltd",
            email="procurement@highlandapparel.com",
            lead_time_days=12,
            minimum_order_value=Decimal("250.00"),
            reliability_score=0.89
        )
        supp_groc = Supplier(
            name="Nature's Harvest Commodities",
            email="fulfillment@naturesharvest.com",
            lead_time_days=5,
            minimum_order_value=Decimal("150.00"),
            reliability_score=0.98
        )
        suppliers = [supp_elec1, supp_elec2, supp_app1, supp_app2, supp_groc]
        db.add_all(suppliers)
        await db.flush()

        # 4. Seed 50 Products
        logger.info(f"Seeding {len(CATEGORIES_AND_SKUS)} Products across Electronics, Apparel, and Groceries...")
        products = []
        sku_to_base_demand = {}

        for sku, name, category, cost, price, base_demand in CATEGORIES_AND_SKUS:
            if category == "Electronics":
                supp = supp_elec1 if "ELEC-IPHONE" in sku or "ELEC-MACBOOK" in sku or "ELEC-SONY" in sku else supp_elec2
            elif category == "Apparel":
                supp = supp_app1 if "APP-TEE" in sku or "APP-JEANS" in sku else supp_app2
            else:
                supp = supp_groc

            prod = Product(
                sku=sku,
                name=name,
                category=category,
                unit_cost=cost,
                unit_price=price,
                default_supplier_id=supp.id
            )
            products.append(prod)
            sku_to_base_demand[sku] = base_demand

        db.add_all(products)
        await db.flush()

        # 5. Generate Reorder Policies & 12 Months of Transactions per SKU
        logger.info("Generating 12-Month Event-Sourced Sales Timeline & Reorder Policies...")
        primary_wh = wh_chi
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=365)

        total_tx_count = 0

        for idx, prod in enumerate(products, 1):
            base_demand = sku_to_base_demand[prod.sku]
            daily_sales = generate_daily_sales_series(base_demand, days=365)
            total_annual_sales = sum(daily_sales)
            avg_daily_d = float(np.mean(daily_sales))
            sigma_d = float(np.std(daily_sales))
            lead_time = prod.default_supplier.lead_time_days if prod.default_supplier else 7

            # Analytical formulas
            ss = calculate_safety_stock(service_level_z=1.65, sigma_demand=sigma_d, lead_time_days=lead_time)
            rop = calculate_reorder_point(avg_daily_demand=avg_daily_d, lead_time_days=lead_time, safety_stock=ss)
            annual_D = avg_daily_d * 365.0
            eoq = calculate_economic_order_quantity(
                annual_demand=annual_D,
                fixed_order_cost=75.00,
                unit_cost=float(prod.unit_cost),
                holding_cost_annual_pct=0.20
            )

            # Reorder Policy
            policy = ReorderPolicy(
                product_id=prod.id,
                warehouse_id=primary_wh.id,
                safety_stock=ss,
                reorder_point=rop,
                economic_order_quantity=eoq,
                service_level_z=1.65,
                lead_time_days=lead_time,
                holding_cost_annual_pct=0.20,
                fixed_order_cost=Decimal("75.00"),
                auto_approve_max_po_value=Decimal("5000.00"),
                is_autonomous=True
            )
            db.add(policy)

            # Seed Initial Inbound Shipment (Day 0) to establish initial stock
            initial_stock_units = int(total_annual_sales * 0.40) + ss + eoq
            init_tx = InventoryTransaction(
                product_id=prod.id,
                warehouse_id=primary_wh.id,
                transaction_type="RECEIPT",
                quantity_delta=initial_stock_units,
                reference_type="OPENING_BALANCE",
                reference_id="INIT-SEED",
                idempotency_key=f"init_{prod.sku}",
                created_at=start_date
            )
            db.add(init_tx)
            total_tx_count += 1

            # Seed Quarterly Replenishment Inbounds (Days 90, 180, 270)
            mid_receipt_days = [90, 180, 270]
            for m_day in mid_receipt_days:
                replenish_qty = int(total_annual_sales * 0.25)
                rec_tx = InventoryTransaction(
                    product_id=prod.id,
                    warehouse_id=primary_wh.id,
                    transaction_type="RECEIPT",
                    quantity_delta=replenish_qty,
                    reference_type="PURCHASE_ORDER",
                    reference_id=f"PO-HIST-D{m_day}",
                    idempotency_key=f"replenish_{prod.sku}_d{m_day}",
                    created_at=start_date + timedelta(days=m_day)
                )
                db.add(rec_tx)
                total_tx_count += 1

            # Record 365 daily SALE transactions
            running_sales_sum = 0
            for day_idx, sale_qty in enumerate(daily_sales):
                if sale_qty <= 0:
                    continue

                tx_time = start_date + timedelta(days=day_idx, hours=random.randint(9, 21), minutes=random.randint(0, 59))
                sale_tx = InventoryTransaction(
                    product_id=prod.id,
                    warehouse_id=primary_wh.id,
                    transaction_type="SALE",
                    quantity_delta=-sale_qty,
                    reference_type="ORDER",
                    reference_id=f"ORD-HIST-{prod.sku[:6]}-{day_idx}",
                    idempotency_key=f"sale_{prod.sku}_{day_idx}",
                    created_at=tx_time
                )
                db.add(sale_tx)
                running_sales_sum += sale_qty
                total_tx_count += 1

            # Total stock calculation for stock_levels
            total_received = initial_stock_units + (int(total_annual_sales * 0.25) * len(mid_receipt_days))
            final_on_hand = max(10, total_received - running_sales_sum)

            stock_level = StockLevel(
                product_id=prod.id,
                warehouse_id=primary_wh.id,
                on_hand=final_on_hand,
                reserved=0,
                available=final_on_hand,
                on_order=0,
                last_reconciled_at=now
            )
            db.add(stock_level)

            if idx % 10 == 0 or idx == len(products):
                logger.info(f"Seeded {idx}/{len(products)} products with full historical timeline...")
                await db.flush()

        # 6. Seed Operational Purchase Orders in Pipeline
        logger.info("Seeding Purchase Orders in varying lifecycle stages...")

        # PO 1: Auto-Approved and SENT (awaiting delivery in 3 days)
        prod1 = products[0]
        po1 = PurchaseOrder(
            po_number="PO-20261108-AUTO01",
            supplier_id=prod1.default_supplier_id,
            warehouse_id=primary_wh.id,
            status="SENT",
            approval_mode="AUTONOMOUS",
            total_cost=Decimal("1598.00"),
            expected_delivery_date=now + timedelta(days=3),
            notes="Autonomous replenishment triggered: effective stock <= ROP."
        )
        db.add(po1)
        await db.flush()
        db.add(POItem(po_id=po1.id, product_id=prod1.id, quantity_ordered=2, quantity_received=0, unit_cost=prod1.unit_cost))

        # PO 2: Large Order exceeding auto-approval threshold -> NEEDS_REVIEW
        prod2 = products[1]  # MacBook 14" ($1250 each, order of 8 = $10,000 > $5000 limit)
        po2 = PurchaseOrder(
            po_number="PO-20261108-REVW02",
            supplier_id=prod2.default_supplier_id,
            warehouse_id=primary_wh.id,
            status="NEEDS_REVIEW",
            approval_mode="MANUAL",
            total_cost=Decimal("10000.00"),
            expected_delivery_date=now + timedelta(days=10),
            notes="Requires human review: PO value $10,000.00 exceeds policy threshold ($5,000.00)."
        )
        db.add(po2)
        await db.flush()
        db.add(POItem(po_id=po2.id, product_id=prod2.id, quantity_ordered=8, quantity_received=0, unit_cost=prod2.unit_cost))

        # Alert for PO 2
        alert_po2 = Alert(
            alert_type="PO_NEEDS_REVIEW",
            severity="WARNING",
            product_id=prod2.id,
            warehouse_id=primary_wh.id,
            message="PO PO-20261108-REVW02 value $10,000.00 exceeds autonomous approval limit of $5,000.00.",
            context_data={"po_number": po2.po_number, "total_cost": 10000.00, "limit": 5000.00},
            status="OPEN"
        )
        db.add(alert_po2)

        # PO 3: CONFIRMED delivery (arriving tomorrow)
        prod3 = products[4]  # USB-C Cable
        po3 = PurchaseOrder(
            po_number="PO-20261108-CONF03",
            supplier_id=prod3.default_supplier_id,
            warehouse_id=primary_wh.id,
            status="CONFIRMED",
            approval_mode="AUTONOMOUS",
            total_cost=Decimal("650.00"),
            expected_delivery_date=now + timedelta(days=1),
            confirmed_delivery_date=now + timedelta(days=1),
            notes="Supplier confirmed via EDI. Tracking: FDX-78901234."
        )
        db.add(po3)
        await db.flush()
        db.add(POItem(po_id=po3.id, product_id=prod3.id, quantity_ordered=100, quantity_received=0, unit_cost=prod3.unit_cost))

        # Generate sample PDF for PO 1
        items_pdf = [{
            "sku": prod1.sku,
            "name": prod1.name,
            "quantity_ordered": 2,
            "unit_cost": float(prod1.unit_cost)
        }]
        pdf_path = PurchaseOrderPDFGenerator.generate_pdf(
            po_number=po1.po_number,
            supplier_name="Apex Global Electronics",
            supplier_email="sales@apex-electronics.com",
            warehouse_name=primary_wh.name,
            warehouse_code=primary_wh.code,
            created_at=po1.created_at,
            expected_delivery=po1.expected_delivery_date,
            items=items_pdf,
            total_cost=po1.total_cost,
            status="SENT",
            approval_mode="AUTONOMOUS"
        )
        po1.pdf_storage_path = pdf_path

        await db.commit()
        logger.info(
            f"Seeding complete! Seeded: 2 Users, 3 Warehouses, 5 Suppliers, "
            f"50 Products, 50 Policies, 3 Active POs, and {total_tx_count} Transactions."
        )


if __name__ == "__main__":
    asyncio.run(seed_database(clear_existing=True))
