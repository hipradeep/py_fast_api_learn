# py_fast_api_learn

A production-structured **Users / Orders / Inventory** REST API built with **FastAPI + SQLModel + PostgreSQL + Alembic**.

Placing an order decrements stock inside a locked transaction; cancelling it puts the stock back.
Every quantity change is written to an immutable `stock_movements` audit log.

## Stack

| Concern | Choice |
|---|---|
| Web framework | FastAPI 0.142 (Pydantic v2) |
| ORM | SQLModel 0.0.47 on SQLAlchemy 2.0 |
| Database | PostgreSQL 16 via psycopg 3 |
| Migrations | Alembic (autogenerate) |
| Settings | pydantic-settings + `.env` |
| Tests | pytest + TestClient (37 tests) |

## Layout

```
py_fast_api_learn/
├── app/
│   ├── main.py                  # app factory, CORS, exception handlers, lifespan
│   ├── core/
│   │   ├── config.py            # Settings (env driven), computes the DB URL
│   │   ├── database.py          # engine, session dependency (commit/rollback)
│   │   └── exceptions.py        # domain errors -> HTTP status codes
│   ├── models/                  # SQLModel tables + enums
│   │   ├── base.py              # TimestampMixin, utc_now
│   │   ├── enums.py             # OrderStatus, StockMovementType, transition rules
│   │   ├── user.py  product.py  order.py  stock_movement.py
│   ├── schemas/                 # Pydantic Create/Update/Read + Page[T]
│   ├── repositories/            # data access only (all SQLAlchemy queries)
│   ├── services/                # business rules and transaction boundaries
│   │   ├── user_service.py  inventory_service.py  order_service.py
│   └── api/
│       ├── deps.py              # DI: SessionDep, service deps, PaginationDep
│       └── v1/
│           ├── router.py
│           └── endpoints/       # health.py users.py inventory.py orders.py
├── alembic/                     # migration environment + versions
├── scripts/seed.py              # demo data
├── tests/                       # pytest suite
├── .env / .env.example
├── alembic.ini
└── requirements.txt
```

Layering is strictly one-directional: **endpoints → services → repositories → models**.
Endpoints contain no SQL, repositories contain no business rules.

## Data model

| Table | Purpose |
|---|---|
| `users` | People who place orders. `email` unique, soft delete via `is_active`. |
| `products` | Sellable items. `sku` unique, `quantity_in_stock`, `reorder_level`. |
| `orders` | Order header. `reference` (`ORD-000042`), status enum, money totals. |
| `order_items` | Lines. Stores `unit_price` and `product_name_snapshot` at purchase time. |
| `stock_movements` | Append-only audit of every stock delta. |

## Business rules

**Inventory**
- All stock changes go through one internal method, so the audit log cannot be bypassed.
- Stock can never go negative; attempting it returns `400 business_rule_violation`.
- A product at or below `reorder_level` is flagged `is_low_stock`.

**Orders**
- Every line is validated *before* any stock is touched, so a rejected order changes nothing.
- Product rows are locked with `SELECT ... FOR UPDATE` while checking and decrementing,
  which prevents concurrent orders from overselling the same row.
- Money uses `Decimal` with explicit `ROUND_HALF_UP` quantisation — no float arithmetic.
- Status flow, and cancelling is only allowed before shipping:

```
pending ──> confirmed ──> shipped ──> delivered
   │            │
   └────────────┴──> cancelled
```

- Cancelling restores every line's stock and stamps `cancelled_at`. It re-checks
  availability first, so a cancellation never fails if stock was meanwhile adjusted.
- Deleted/cancelled orders keep `unit_price` and `product_name_snapshot`, so historic
  invoices stay correct even after a product is renamed or repriced.

## Setup

```bash
cd py_fast_api_learn

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

Database connection lives in `.env` (already set for this project):

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=1234
POSTGRES_DB=py_crud
```

## Run

```bash
alembic upgrade head                 # create the tables
python -m scripts.seed --force       # optional demo data
uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Readiness (checks the DB): http://127.0.0.1:8000/api/v1/health/ready

## Tests

```bash
pytest
```

The suite runs against the configured database and truncates its own rows, so point
`POSTGRES_DB` at a scratch database if you care about the contents of `py_crud`.

## API

All routes are prefixed with `/api/v1`.

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/health/ready` | Readiness incl. database connectivity |

### Users
| Method | Path | Description |
|---|---|---|
| GET | `/users` | List, paginated (`page`, `page_size`, `search`, `is_active`) |
| POST | `/users` | Create (201) |
| GET | `/users/{id}` | Fetch one |
| PATCH | `/users/{id}` | Partial update |
| POST | `/users/{id}/deactivate` | Soft deactivate |
| DELETE | `/users/{id}` | Delete (204); refused while open orders exist |

### Inventory
| Method | Path | Description |
|---|---|---|
| GET | `/inventory/products` | List, `search` / `is_active` / `low_stock` filters |
| POST | `/inventory/products` | Create (201); opens an `initial_stock` movement |
| GET | `/inventory/products/{id}` | Fetch one |
| PATCH | `/inventory/products/{id}` | Update metadata (never stock) |
| POST | `/inventory/products/{id}/stock` | Signed adjustment, e.g. `{"quantity_delta": -3}` |
| POST | `/inventory/products/{id}/restock` | Add stock, `?quantity=10` |
| GET | `/inventory/products/{id}/movements` | Stock audit history |
| GET | `/inventory/low-stock` | Items at or below reorder level |
| GET | `/inventory/summary` | KPIs incl. total inventory value |

### Orders
| Method | Path | Description |
|---|---|---|
| GET | `/orders` | List, `user_id` / `status` filters |
| POST | `/orders` | Place an order (201); decrements stock atomically |
| GET | `/orders/{id}` | Fetch one with lines |
| PATCH | `/orders/{id}/status` | Move status; cancelling restores stock |
| POST | `/orders/{id}/cancel` | Cancel and restock, `?reason=...` |

## Worked example

```bash
# 1. create a user
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"email": "dana@example.com", "full_name": "Dana Reed"}'

# 2. add a product with opening stock
curl -X POST http://127.0.0.1:8000/api/v1/inventory/products \
  -H "Content-Type: application/json" \
  -d '{"sku": "MOUSE-9", "name": "Wireless Mouse", "unit_price": "29.99",
       "quantity_in_stock": 40, "reorder_level": 10}'

# 3. place an order (stock drops to 37, tax 8%)
curl -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "tax_rate": "0.08",
       "items": [{"product_id": 1, "quantity": 3}]}'

# 4. cancel it (stock returns to 40)
curl -X POST "http://127.0.0.1:8000/api/v1/orders/1/cancel?reason=changed_mind"

# 5. inspect the audit trail
curl http://127.0.0.1:8000/api/v1/inventory/products/1/movements
```

## Error format

```json
{
  "code": "business_rule_violation",
  "message": "Insufficient stock for MOUSE-9 (Wireless Mouse): requested 5, available 2",
  "details": {"product_id": 1, "sku": "MOUSE-9", "requested": 5, "available": 2}
}
```

`not_found` 404 · `conflict` 409 · `validation_error` 422 · `business_rule_violation` 400
· `integrity_error` 409 · `internal_error` 500.

## Notes

- Auth is intentionally out of scope; `users` is a CRUD resource here. When you add it,
  put a `get_current_user` dependency in `app/api/deps.py` and guard the routers.
- Each request is one transaction: `get_session` commits on success and rolls back on
  any exception, so services only ever need `flush()`.
- Migrations are the source of truth. Avoid `create_db_and_tables()` in production.