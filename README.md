# Autonomous Inventory Management System ⚡📦

[![CI Pipeline](https://github.com/chinmaybhatt/inventory-managemnet/actions/workflows/ci.yml/badge.svg)](https://github.com/chinmaybhatt/inventory-managemnet/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0.28-red.svg)](https://www.sqlalchemy.org/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14.2.15-black.svg)](https://nextjs.org/)
[![Test Coverage](https://img.shields.io/badge/coverage-Replenishment%2096%25%20%7C%20Ledger%2091%25-brightgreen.svg)]()

A pure software-based, autonomous inventory management engine engineered for zero routine human intervention. Stock is tracked purely via immutable, event-sourced financial-grade ledger transactions (`SALE`, `RECEIPT`, `RETURN`, `DAMAGE`, `ADJUSTMENT`, `TRANSFER`).

Routine inventory decisions—order ingestion, atomic reservations, machine learning demand forecasting, stochastic reorder point ($ROP$) and economic order quantity ($EOQ$) evaluations, automated purchase order creation, vector PDF rendering, and supplier dispatch—run automatically. **Human operators are alerted strictly on business exceptions.**

---

## 🏛 System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Ingestion Layer"]
        B2B["B2B REST API Orders"] --> IngestService["Order Service"]
        Shopify["Shopify Webhooks\n(HMAC-SHA256)"] --> IngestService
    end

    subgraph Ledger["2. Event-Sourced Ledger"]
        IngestService -->|Atomic Reservation| DistLock["Redis Distributed Lock\nsorted(product_ids)"]
        DistLock --> LedgerTx["inventory_transactions\n(Immutable Audit Log)"]
        LedgerTx --> CacheView["stock_levels\n(Materialized Cache)"]
    end

    subgraph Analytics["3. Forecasting & ML Engine"]
        HistSales["12-Month Sales History"] --> MLForecaster["Dual-Engine Forecaster"]
        MLForecaster -->|Cold Start (<90d)| EWMA["EWMA Moving Average"]
        MLForecaster -->|Mature (>=90d)| LightGBM["LightGBM + Lag Features\n(7d & 30d Horizon)"]
        LightGBM --> Backtest["WAPE / MAPE Backtesting"]
        Backtest --> MLflow["MLflow Model Registry"]
    end

    subgraph Replenishment["4. Autonomous Replenishment"]
        CacheView --> RepEngine["Replenishment Engine"]
        MLForecaster --> RepEngine
        RepEngine --> Formula["Stochastic Math:\nSS = Z * σ * √L\nROP = d * L + SS\nEOQ = √(2DS/H)"]
        Formula --> Trigger{"(on_hand + on_order\n- reserved) <= ROP?"}
        Trigger -- Yes --> Threshold{"PO Value < Auto-Limit?"}
        Threshold -- Yes --> AutoPO["Status: AUTO_APPROVED\nMode: AUTONOMOUS"]
        Threshold -- No --> ManualPO["Status: NEEDS_REVIEW\nAlert Generated"]
    end

    subgraph Gateway["5. Supplier Gateway & GRN"]
        AutoPO --> PDFGen["ReportLab Vector PDF\nPO Generator"]
        PDFGen --> Dispatch["Supplier Gateway\n(Mock REST / SMTP)"]
        Dispatch --> Supplier["External Supplier"]
        Supplier -->|ACK Webhook| GatewayIn["Delivery Confirmation (ETA)"]
        Supplier -->|Physical Shipment| GRN["Goods Receipt Note (GRN) API"]
        GRN -->|RECEIPT Tx| LedgerTx
        GRN -->|Mark Completed| AutoPO
    end

    subgraph Exceptions["6. Exception & Anomaly Watchdog"]
        AuditJob["Celery Beat Periodic Sweeps"] --> AnomalyEng["Anomaly Engine"]
        AnomalyEng -->|Audit Sum(Tx) != on_hand| DriftAlert["Stock Drift Alert"]
        AnomalyEng -->|Daily Sales > μ + 3σ| SpikeAlert["Demand Spike Alert"]
        AnomalyEng -->|0 Sales > 60 Days| DeadAlert["Dead Stock Alert"]
        AnomalyEng -->|ETA < Now()| DelayAlert["Supplier Delay Alert"]
        DriftAlert --> Human["Human Manager Intervention"]
        SpikeAlert --> Human
        DeadAlert --> Human
        DelayAlert --> Human
    end
```

---

## 🌟 Key Features

1. **Event-Sourced Inventory Ledger**
   - Stock is **NEVER** a mutable stored number; it is mathematically derived from the integral sum of immutable `inventory_transactions`.
   - `stock_levels` acts as a high-performance materialized cache with row-level locks (`SELECT FOR UPDATE`) and multi-SKU sorted Redis distributed locks (`stock:{product_id}:{warehouse_id}`) to eliminate race conditions and negative inventory.
   - Idempotency keys enforced on all writes (`POST /api/v1/orders/`, `POST /api/v1/ledger/adjustment`, Shopify webhooks).

2. **Autonomous Order Ingestion**
   - High-throughput REST API with payload validation.
   - Shopify-compatible webhook receiver with HMAC-SHA256 signature verification (`X-Shopify-Hmac-Sha256`).

3. **Dual-Horizon Demand Forecasting**
   - **Cold Start (< 90 days data)**: Exponentially Weighted Moving Average (EWMA) with recent trend weighting.
   - **Mature ($\ge$ 90 days data)**: LightGBM regressor trained with rolling demand lags (7d, 14d, 28d), day-of-week, day-of-year, and month seasonality.
   - Model validation with Weighted Absolute Percentage Error (**WAPE**) and Mean Absolute Percentage Error (**MAPE**).
   - Artifact logging and experiment version tracking via **MLflow**.

4. **Stochastic Replenishment Engine**
   - **Safety Stock**: $SS = Z \times \sigma_{\text{demand}} \times \sqrt{L}$ (where $Z$ is the Gaussian critical value for target service levels, e.g., 95% = 1.645, 99% = 2.326).
   - **Reorder Point**: $ROP = (\bar{d} \times L) + SS$.
   - **Economic Order Quantity**: $EOQ = \sqrt{\frac{2 \times D \times S}{H}}$ (where $D$ is annual demand, $S$ is fixed order cost, and $H$ is annual unit holding cost).
   - Reorder triggered autonomously when: $(\text{on\_hand} + \text{on\_order} - \text{reserved}) \le ROP$.

5. **PO Generation & Auto-Approval Engine**
   - Automatically clusters triggered SKUs by supplier and warehouse.
   - Configurable per-policy auto-approval limits (`auto_approve_max_po_value`). POs below threshold immediately enter `AUTO_APPROVED` status; POs above threshold switch to `NEEDS_REVIEW` and raise high-severity alerts.
   - Production-grade vector PDF purchase orders rendered via ReportLab with corporate branding, itemized tables, currency formatting, and verification hashes.

6. **Supplier Gateway & Goods Receipt Note (GRN)**
   - Dispatches POs via simulated REST adapter and SMTP email mock with attached vector PDFs.
   - Inbound supplier acknowledgment webhook (`/api/v1/suppliers/po-acknowledgment`) parses confirmed ETAs and tracking numbers.
   - Inbound Goods Receipt Note API (`/api/v1/goods-receipt/`) atomically debits `on_order`, increments `on_hand` via `RECEIPT` ledger transactions, and advances PO status to `PARTIALLY_RECEIVED` or `COMPLETED`.

7. **Proactive Anomaly & Exception Watchdog**
   - **Stock Drift Detection**: Reconciles materialized cache against sum of transactions; alerts and auto-corrects on disparity.
   - **Demand Spike Detection**: Flags sales exceeding baseline mean by more than $3\sigma$.
   - **Dead Stock Detection**: Flags SKUs with zero consumption over 60 days.
   - **Supplier Delay Detection**: Identifies open POs exceeding confirmed ETA and dispatches automated supplier escalation notifications.

8. **Celery Beat Background Daemon**
   - Nightly ML forecast refresh & model retraining (02:00 UTC).
   - Hourly autonomous ROP replenishment evaluation (every hour).
   - Daily dead stock detection (03:00 UTC).
   - Continuous supplier delivery tracking (every 4 hours).
   - Daily ledger integrity and stock drift audit (04:00 UTC).

9. **Next.js 14 Modern Web Dashboard**
   - Responsive UI built with Tailwind CSS, Lucide React, and Recharts.
   - 6 core views: Inventory Overview, Immutable Ledger Trail, Demand Forecasts, Purchase Order Pipeline, Exceptions & Alerts Feed, and Autonomy Policies.

---

## 🗄 Database Schema (13 Core Tables)

| Table | Purpose |
|---|---|
| `users` | Role-based authentication (`admin`, `viewer`) with bcrypt password hashing. |
| `products` | Master SKU catalog, unit costs, selling prices, and default suppliers. |
| `warehouses` | Multi-facility inventory distribution locations. |
| `inventory_transactions` | Immutable, append-only financial-grade ledger of all stock mutations. |
| `stock_levels` | High-speed cached inventory view (`on_hand`, `reserved`, `on_order`, `available`). |
| `orders` | Customer sales orders with atomic reservation tracking (`RESERVED`, `FULFILLED`, `CANCELLED`). |
| `order_items` | Line items detailing product SKU, quantity, and unit price. |
| `suppliers` | Supplier directory, lead times, reliability scores, and contact endpoints. |
| `purchase_orders` | Autonomous & manual procurement orders (`DRAFT`, `AUTO_APPROVED`, `SENT`, `CONFIRMED`, `COMPLETED`). |
| `po_items` | PO line items with quantities ordered vs received. |
| `forecasts` | ML forecasted point predictions with upper/lower prediction intervals. |
| `reorder_policies` | Autonomous replenishment rules, safety stock, ROP, EOQ, and approval limits. |
| `alerts` | Exception and anomaly records with severity, context data, and human resolution notes. |
| `audit_logs` | System security audit trail for sensitive administrative operations. |

---

## 🚀 Quickstart Guide

### Option 1: Docker Compose (Production Stack)

Start all services (PostgreSQL 16, Redis 7.2, FastAPI backend, Celery worker, Celery Beat, Next.js frontend):

```bash
# 1. Clone repository
git clone https://github.com/chinmaybhatt/inventory-managemnet.git
cd inventory-managemnet

# 2. Configure environment
cp .env.example .env

# 3. Spin up full containerized stack
docker-compose up --build -d

# 4. Apply migrations and seed 12-month realistic dataset (50 SKUs, 18,000+ transactions)
docker-compose exec backend alembic upgrade head
docker-compose exec backend python scripts/seed_data.py
```

- **Frontend Dashboard**: http://localhost:3000
- **FastAPI OpenAPI Swagger Docs**: http://localhost:8000/docs
- **MLflow Tracking Server**: http://localhost:5000

---

### Option 2: Local Development Setup

#### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- PostgreSQL 16 & Redis 7

```bash
# 1. Setup Backend Virtual Environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure Environment
cp .env.example .env

# 3. Run Database Migrations
alembic upgrade head

# 4. Seed Realistic 12-Month Sales & Catalog Data
python scripts/seed_data.py

# 5. Start Backend Server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. (In separate terminal) Start Celery Worker & Beat Scheduler
celery -A backend.app.tasks.celery_app worker -B --loglevel=info

# 7. (In separate terminal) Setup and Start Frontend
cd frontend
npm install
npm run dev
```

---

## 🧪 Comprehensive Testing & Verification

The test suite exercises all edge cases, concurrency locks, stochastic math formulas, ledger invariants, ML pipelines, and Celery jobs:

```bash
# Run full test suite with coverage report
.venv/bin/pytest --cov=backend.app.services --cov=backend.app.ml --cov=backend.app.tasks tests/
```

### Coverage Highlights

```text
Name                                            Stmts   Miss  Cover
-------------------------------------------------------------------
backend/app/services/replenishment_math.py         28      1    96%
backend/app/services/ledger_service.py            107     10    91%
backend/app/services/anomaly_service.py           149      3    98%
backend/app/services/goods_receipt_service.py      55      0   100%
backend/app/services/po_pdf_generator.py           52      0   100%
backend/app/services/supplier_gateway.py           86     11    87%
backend/app/ml/forecaster.py                      122     16    87%
backend/app/ml/metrics.py                          23      2    91%
-------------------------------------------------------------------
TOTAL                                            1183    256    78%
============================= 43 passed in 22.36s ==============================
```

---

## 📡 API Usage & Reference

### 1. Authentication
```bash
# Obtain JWT bearer token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=adminpassword123"
```

### 2. Ingest Customer Order (Atomic Stock Reservation)
```bash
curl -X POST http://localhost:8000/api/v1/orders/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "order_number": "ORD-2026-001",
    "warehouse_id": "wh_id_here",
    "items": [
      {"product_id": "prod_id_here", "quantity": 10, "unit_price": "49.99"}
    ],
    "idempotency_key": "order_idem_key_001"
  }'
```

### 3. Ingest Shopify Webhook Order (HMAC-SHA256 Signed)
```bash
curl -X POST http://localhost:8000/api/v1/orders/webhook/shopify \
  -H "X-Shopify-Hmac-Sha256: <BASE64_HMAC_SIGNATURE>" \
  -H "Content-Type: application/json" \
  -d '{
    "id": 892348923,
    "name": "#1001",
    "line_items": [
      {"sku": "SKU-AUDIO-001", "quantity": 5, "price": "129.99"}
    ]
  }'
```

### 4. Trigger Autonomous Replenishment Evaluation Sweep
```bash
curl -X POST http://localhost:8000/api/v1/replenishment/evaluate \
  -H "Authorization: Bearer <TOKEN>"
```

### 5. Inbound Goods Receipt Note (GRN) Processing
```bash
curl -X POST http://localhost:8000/api/v1/goods-receipt/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "po_number": "PO-20261108-ABCD",
    "warehouse_id": "wh_id_here",
    "items": [
      {"product_id": "prod_id_here", "quantity_received": 100, "condition": "GOOD"}
    ]
  }'
```

### 6. On-Demand Zero-Drift & Anomaly Audit Sweep
```bash
curl -X POST http://localhost:8000/api/v1/alerts/audit \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 📂 Project Structure

```text
inventory-management/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI (Backend tests + Frontend build)
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py          # FastAPI dependencies (Auth, DB session, Roles)
│   │   │   └── v1/              # Versioned API routes (Auth, Orders, Ledger, POs, etc.)
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic v2 settings (.env loader)
│   │   │   ├── database.py      # SQLAlchemy 2.0 async engine & sessionmaker
│   │   │   ├── redis.py         # Redis connection pool & distributed locks
│   │   │   └── security.py      # JWT encoding/decoding & bcrypt password hashing
│   │   ├── ml/
│   │   │   ├── feature_engineering.py  # Lag features, calendar cyclical transforms
│   │   │   ├── forecaster.py    # EWMA cold start + LightGBM forecaster
│   │   │   └── metrics.py       # WAPE & MAPE error scoring
│   │   ├── models/              # 13 SQLAlchemy 2.0 ORM Declarative Models
│   │   ├── schemas/             # Pydantic v2 validation & response models
│   │   ├── services/            # Business logic (Ledger, Order, Replenishment, Gateway, GRN, Anomaly)
│   │   ├── tasks/               # Celery app & periodic Celery Beat task definitions
│   │   └── main.py              # FastAPI application bootstrap & CORS
│   └── Dockerfile               # Production Python 3.11 container
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js 14 App Router pages (Dashboard, Ledger, Forecasts, etc.)
│   │   ├── components/          # Reusable UI components (Sidebar, MetricCard, Chart, AlertFeed)
│   │   └── lib/                 # API client utilities & TypeScript types
│   ├── package.json
│   ├── tailwind.config.ts
│   └── Dockerfile               # Production Next.js standalone container
├── scripts/
│   └── seed_data.py             # 12-Month synthetic sales seeder (50 SKUs, 18k+ txs, 0 drift)
├── tests/
│   ├── conftest.py              # Pytest async fixtures (SQLite async engine, HTTP client, JWT)
│   ├── integration/
│   │   └── test_e2e_lifecycle.py # Full 12-step autonomous lifecycle integration test
│   └── unit/                    # Unit test suites covering Phases 1 through 7
├── docker-compose.yml           # Multi-container orchestration (DB, Redis, App, Celery, UI)
├── alembic.ini                  # Alembic migration configuration
├── requirements.txt             # Python dependencies
└── README.md                    # System documentation
```

---

## 🛡 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

