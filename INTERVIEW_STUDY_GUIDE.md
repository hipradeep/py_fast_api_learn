# FastAPI Interview Study Guide — `py_fast_api_learn`

A deep-dive guide that turns this repository into an interview-prep lab. Every claim points at
real code (`file:line`) so you can verify it, run it, and then explain it out loud.

This is **not** a FastAPI tutorial. It is a map of *this* codebase, ordered so that each module
unlocks the next, plus the questions interviewers actually ask and the answers you should give.

---

## How to use this guide

Each module follows the same loop:

1. **Read** the listed files, in the listed order.
2. **Trace** one real request/statement through every layer on paper.
3. **Run** the exercise (curl / pytest / psql) and observe the behaviour.
4. **Say** the checkpoint answers aloud in under 60 seconds each.

If you can do step 4 without looking, you are interview-ready on that topic. If you cannot,
redo steps 1–3 the next day.

### Reading order and time budget

| # | Module | Key files | Est. time |
|---|---|---|---|
| 0 | Setup and verification | `.env`, `alembic.ini`, `pytest.ini` | 15 min |
| 1 | Request lifecycle and app wiring | `app/main.py`, `app/api/v1/router.py`, `endpoints/health.py` | 30 min |
| 2 | Dependency injection | `app/api/deps.py` | 45 min |
| 3 | Pydantic v2 schemas and validation | `app/schemas/*` | 60 min |
| 4 | Domain models, enums, relationships | `app/models/*` | 60 min |
| 5 | Session and transaction boundary | `app/core/database.py` | 45 min |
| 6 | Repositories and SQL | `app/repositories/*` | 60 min |
| 7 | Services and the order state machine | `app/services/*` | 90 min |
| 8 | Domain errors mapped to HTTP | `app/core/exceptions.py`, `app/main.py:53` | 45 min |
| 9 | Money, Decimal, and quantisation | `app/services/order_service.py:23` | 30 min |
| 10 | Concurrency: locking and oversell | `app/repositories/product.py:22` | 60 min |
| 11 | Migrations with Alembic | `alembic/env.py`, `alembic/versions/*` | 30 min |
| 12 | Testing strategy | `tests/*` | 60 min |
| 13 | Dead code and design critique | whole repo | 30 min |

Total: roughly 11–13 hours. Do it in 3–4 sittings.

---

## Part 0 — Setup and verification

Your environment was verified while writing this guide: the venv works, PostgreSQL is reachable at
`localhost:5432/py_crud`, Alembic is at revision `f5e85f10ac53 (head)`, and pytest collects
**37 tests**. If any of that stops being true, fix it before studying — half the exercises fail
opaquely without a database.

```powershell
cd py_fast_api_learn
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt    # only if the venv is new

alembic upgrade head               # create/verify tables
python -m scripts.seed --force     # optional demo data
uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs
pytest                              # 37 tests, needs the DB
```

### PowerShell gotcha that will waste an hour

In PowerShell 5.1, `curl` is an **alias for `Invoke-WebRequest`**, not the real curl. Every
`-X POST`, `-d '{...}'` and `-H` example in the README and in this guide fails confusingly.
Always call the real binary:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/users -H "Content-Type: application/json" -d '{"email":"a@b.com","full_name":"A"}'
```

or use the native cmdlets, which are nicer on Windows:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/users `
  -ContentType 'application/json' -Body '{"email":"a@b.com","full_name":"A"}'
```

### Protect your data: use a scratch database for tests

`tests/conftest.py:19` (`clean_db`) issues real `DELETE` statements against the tables in
`POSTGRES_DB` before and after **every** test. Running `pytest` therefore wipes `py_crud`.
`tests/conftest.py:21` opens a session against the production `engine` — there is no test database
and no rollback-per-test wrapper.

Create a scratch DB once, and point the app at it while studying:

```powershell
psql -U postgres -c "CREATE DATABASE py_crud_test"
$env:POSTGRES_DB = "py_crud_test"     # env var wins over .env in pydantic-settings
alembic upgrade head
pytest
```

This is itself an interview answer: **env vars take precedence over `.env`** in
`pydantic-settings` (`.env` is only the fallback layer), which is why `.env` holds safe defaults
and real deployments inject secrets from the environment.

### Two switches worth knowing

- `DB_ECHO=True` in `.env` makes SQLAlchemy print every statement — the fastest way to see
  `SELECT ... FOR UPDATE`, the `selectin` loaders, and the two pagination queries per list endpoint.
- `uvicorn app.main:app --reload` restarts on save. Use `--workers 4` (Linux/macOS) or
  `--workers 4 --worker-class uvicorn.workers.UvicornWorker` on Windows to see how the code behaves
  under concurrency (relevant to Module 10).

---

## Module 1 — Request lifecycle and app wiring

**Files:** `app/main.py`, `app/api/v1/router.py`, `app/api/v1/endpoints/health.py`, `app/core/config.py`

### Concepts

- **App factory** — `create_app()` at `app/main.py:28` returns a configured `FastAPI`; the module-level
  `app = create_app()` at `app/main.py:79` is the ASGI callable Uvicorn imports.
- **Lifespan** — `app/main.py:21` uses `@asynccontextmanager`. Code before `yield` is startup, code
  after is shutdown. This repo only logs; a real app creates the HTTP client, warms caches, or runs
  `create_db_and_tables` here. Lifespan replaced the older `@app.on_event("startup")` hooks.
- **Middleware** — `app/main.py:39` adds `CORSMiddleware`. Middleware wraps *every* request
  (process → call_next → response) and is the right place for request IDs, timing, and auth.
- **Routers** — `app/api/v1/router.py:5` aggregates the four endpoint routers, then
  `app/main.py:47` mounts the aggregate under `settings.API_V1_PREFIX` (`/api/v1`). Each router
  carries its own prefix (`/orders` at `endpoints/orders.py:10`) and tags, which is what makes
  Swagger group by tag.
- **Two health probes** — `endpoints/health.py:12` is *liveness* ("the process is up", no
  dependencies) and `endpoints/health.py:17` is *readiness* ("the DB answers", it injects
  `SessionDep` and runs `SELECT 1`). Kubernetes uses liveness to decide whether to **restart** a
  pod and readiness to decide whether to **route traffic** to it. Conflating them causes restart
  storms during a database blip.
- **Settings** — `app/core/config.py:8` is a `BaseSettings` class; `app/core/config.py:38` derives
  the DSN with `@computed_field`, so there is exactly one source of truth for the connection
  string; `app/core/config.py:47` caches it with `@lru_cache` so `.env` is parsed once.

### Trace: `GET /api/v1/`

1. Uvicorn resolves `app.main:app`.
2. CORS middleware wraps the call (`app/main.py:39`).
3. Router tree resolves: `/api/v1` (prefix from settings) + `/` (the hidden route at
   `endpoints/health.py:23`, which is `include_in_schema=False` so it stays out of the docs).
4. The handler has no dependencies, so FastAPI calls it directly and serialises the `dict[str, str]`
   return annotation.
5. No exception → no handler runs.

### Exercise

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
curl.exe http://127.0.0.1:8000/api/v1/health/ready
curl.exe http://127.0.0.1:8000/api/v1/          # hidden from /docs but alive
curl.exe -i http://127.0.0.1:8000/api/v1/ORDERS  # wrong case -> 404, proof of exact routing
curl.exe http://127.0.0.1:8000/openapi.json | python -c "import json,sys;d=json.load(sys.stdin);print(sorted(d['paths']))"
```

Then stop the server and re-run `/health/ready`: it still answers 200 while `/health/ready` would
fail — proof that liveness and readiness are genuinely different signals.

### Checkpoint questions

1. Why an app factory instead of a module-level `app = FastAPI(...)`? (Answer: per-instance config,
   testability, multiple apps in one process, no import-time side effects.)
2. What runs where in the lifespan, and what would you put there?
3. Middleware vs dependency — when do you use which?
4. Difference between liveness and readiness; what breaks if you only have liveness?
5. How does `/api/v1` get prefixed, and how would you add `/api/v2` without breaking v1?

---

## Module 2 — Dependency injection

**File:** `app/api/deps.py` (50 lines, four ideas)

### Concepts

- **Callable dependencies** — `get_user_service(session: SessionDep)` at `app/api/deps.py:36`
  receives the session, builds a service, and returns it. FastAPI resolves the nested dependency
  first.
- **`Annotated` aliases** — `SessionDep = Annotated[Session, Depends(get_session)]`
  (`app/api/deps.py:10`) and `OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]`
  (`app/api/deps.py:50`). This is the modern FastAPI idiom: the signature in the endpoint reads
  `def create_order(payload: OrderCreate, service: OrderServiceDep)` with no `= Depends(...)`
  default noise, and the dependency graph is declared once.
- **Class dependencies** — `Pagination` at `app/api/deps.py:13` is a plain class whose
  `__init__` params are `Query(...)` annotated. FastAPI introspects the signature and injects
  `page`/`page_size`, then exposes derived values as `@property` (`offset` at `app/api/deps.py:24`,
  `limit` at `app/api/deps.py:28`). This is the trick that removes pagination boilerplate from
  every list endpoint.
- **Validation in the dependency** — `Query(ge=1)` and `Query(ge=1, le=settings.MAX_PAGE_SIZE)` mean
  `page=0` or `page_size=1000` is rejected with 422 *before* the handler body runs.
- **Request-scoped lifetime** — the session and the service are created per request and torn down
  when the request ends, which is exactly why a service can safely hold mutable state.

### Trace: dependency graph for `POST /api/v1/orders`

```
create_order(payload: OrderCreate, service: OrderServiceDep)
  └── get_order_service(session: SessionDep)
        └── get_session()            # database.py:30 -> yields Session
  └── OrderCreate                    # body parsed + validated by Pydantic
```

`get_session` uses `yield`, so FastAPI keeps the session open for the whole request and runs the
teardown (commit/rollback/close) after the response is produced — see Module 5.

### Exercise

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/users?page=0"                 # 422 from Query(ge=1)
curl.exe "http://127.0.0.1:8000/api/v1/users?page_size=1000"          # 422 from le=MAX_PAGE_SIZE
curl.exe "http://127.0.0.1:8000/api/v1/users?page=1&page_size=2"      # valid, shows Page[T]
```

Read `app/api/deps.py:16` again after those 422s. That is the whole value proposition: the
validation lives in the dependency, so no handler ever re-checks it.

### Checkpoint questions

1. What is the difference between `Depends(get_session)` and `Security(get_session)`?
2. Why does this project use `Annotated[...]` aliases instead of `x = Depends(...)` defaults?
3. What runs first if a dependency raises? (Answer: FastAPI resolves in declaration order, the
   exception handler runs, and teardown of already-resolved `yield` dependencies still executes.)
4. How would you override a dependency in a test? (`app.dependency_overrides[get_order_service] = ...`)
5. When is a class dependency better than a function dependency?

---

## Module 3 — Pydantic v2 schemas and validation

**Files:** `app/schemas/common.py`, `app/schemas/user.py`, `app/schemas/product.py`, `app/schemas/order.py`

### Concepts

- **Schema ≠ model.** `app/models/*` define the database shape (SQLModel tables). `app/schemas/*`
  define the *wire* contract. `UserCreate` has no `id`; `UserRead` has no write-only fields; the
  API can therefore evolve without migrating the database, and vice versa.
- **Inheritance for reuse** — `UserBase` (`app/schemas/user.py:9`) → `UserCreate` / `UserRead`.
  `ProductUpdate` is written out longhand because PATCH must accept `None` for "not supplied".
- **`ORMModel`** — `app/schemas/common.py:8` sets `from_attributes=True`, which is Pydantic v2's
  replacement for v1's `orm_mode`. Without it, `OrderRead` could not be built from an `Order`
  instance.
- **Declarative constraints** — `Field(min_length=1, max_digits=12, decimal_places=2)` on
  `ProductBase.unit_price` (`app/schemas/product.py:15`) generate both runtime validation and the
  OpenAPI/documentation. `EmailStr` (`app/schemas/user.py:10`) is a real email check — that is why
  `email-validator` is in `requirements.txt`.
- **Cross-field validation** — `@model_validator(mode="after")` at `app/schemas/order.py:34`
  rejects duplicate `product_id` values in one order. This is a *shape* rule, so it belongs in the
  schema (422 for the client) rather than the service (400 business rule).
- **Partial update** — `model_dump(exclude_unset=True)` at `app/services/user_service.py:48` and
  `app/services/inventory_service.py:71` is the PATCH idiom: only fields the client actually sent
  are applied, so `PATCH {"full_name": "X"}` does not wipe `phone`.
- **Generic response envelope** — `Page(BaseModel, Generic[T])` at `app/schemas/common.py:16` with
  `build()` at `app/schemas/common.py:23`. `pages` is integer ceiling division, computed once.
- **`computed_field`** — `ProductRead.is_low_stock` (`app/schemas/product.py:48`) is a derived value
  that appears in the JSON and in the docs without being a database column.

### Trace: `POST /api/v1/orders` with a bad body

FastAPI validates `OrderCreate` *before* the handler. Duplicate product ids → the model validator
raises → 422 with a `loc` pointing at `body`. The service never runs, so no stock is touched.
Compare with an oversell attempt, which passes schema validation and fails in the service with 400
(`app/services/order_service.py:76`) — that difference is a favourite interview question.

### Exercise

```powershell
# 422: empty items (min_length=1)
curl.exe -X POST http://127.0.0.1:8000/api/v1/orders -H "Content-Type: application/json" `
  -d '{"user_id":1,"items":[]}'

# 422: quantity must be > 0
curl.exe -X POST http://127.0.0.1:8000/api/v1/orders -H "Content-Type: application/json" `
  -d '{"user_id":1,"items":[{"product_id":1,"quantity":0}]}'

# 422: tax_rate > 1
curl.exe -X POST http://127.0.0.1:8000/api/v1/orders -H "Content-Type: application/json" `
  -d '{"user_id":1,"tax_rate":1.5,"items":[{"product_id":1,"quantity":1}]}'

# 422: not an email
curl.exe -X POST http://127.0.0.1:8000/api/v1/users -H "Content-Type: application/json" `
  -d '{"email":"nope","full_name":"X"}'
```

Now open `/docs` and click "Try it out". Note that every constraint above is documented, and that
the generated schema (`components.schemas.OrderCreate`) is machine-readable — that is the real
interview point: **validation is a contract, not a pile of if-statements**.

### Checkpoint questions

1. `model_validator` vs `field_validator`: when each?
2. Why does `from_attributes=True` exist, and what breaks without it?
3. How do you implement PATCH correctly, and what is the bug in `payload.dict()` without
   `exclude_unset`?
4. When do you use `response_model` and what does it protect you from?
5. Why put the "no duplicate products" rule in the schema rather than the service?

---

## Module 4 — Domain models, enums, relationships

**Files:** `app/models/base.py`, `app/models/enums.py`, `app/models/user.py`, `app/models/product.py`,
`app/models/order.py`, `app/models/stock_movement.py`, `app/models/__init__.py`

### Concepts

- **SQLModel** — one class is both a Pydantic model and a SQLAlchemy table (`table=True`). The
  benefit is less boilerplate; the cost is that a single class must satisfy both worlds, which is
  exactly why this repo keeps models and schemas separate anyway.
- **`TimestampMixin`** — `app/models/base.py:10` gives every table `created_at` /
  `updated_at`; `onupdate=utc_now` at `app/models/base.py:17` is a *server-side SQL* expression
  fired by SQLAlchemy on UPDATE. `utc_now()` at `app/models/base.py:6` returns a timezone-aware
  datetime — never `datetime.now()` naive, or you get mixed-awareness bugs.
- **Enums with stable storage** — `OrderStatus` is a `str` enum with lowercase values
  (`app/models/enums.py:4`). The `values_callable` trick at `app/models/order.py:17` makes Postgres
  store `"pending"`, not `"PENDING"`, so renaming the Python member never breaks stored data. You
  can see the result in the generated migration: `sa.Enum('pending', 'confirmed', ...)`
  (`alembic/versions/f5e85f10ac53_initial_schema.py:59`). This is a top-tier interview answer.
- **The state machine as data** — `ALLOWED_STATUS_TRANSITIONS` (`app/models/enums.py:12`) is a
  dict of sets, and `TERMINAL_STATUSES` (`app/models/enums.py:20`) marks absorbing states. The
  rules live in one place, testable without a database.
- **Snapshot columns** — `OrderItem.unit_price` and `product_name_snapshot`
  (`app/models/order.py:77`). A line stores what was true at purchase time, so renaming or
  repricing a product cannot corrupt historical invoices. Naming this pattern unprompted is a
  strong signal.
- **Append-only audit log** — `StockMovement` (`app/models/stock_movement.py:20`) records
  `quantity_change` and `quantity_after` for every change, with a nullable `order_id` so manual
  adjustments are distinguishable from order-driven ones.
- **Relationship loading** — `lazy="selectin"` on `Order.items` (`app/models/order.py:48`),
  `User.orders` (`app/models/user.py:20`), `Product.stock_movements`
  (`app/models/product.py:28`). Without it, serialising `OrderRead.items` would emit one extra
  query per order (N+1).

### Exercise

Turn on `DB_ECHO=True`, restart, then:

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/orders?page_size=3"
```

Count the SQL statements. Two for the page (`SELECT ... LIMIT`, `SELECT count(*)`) plus **one**
joined load for the items thanks to `selectin`. Then remove `sa_relationship_kwargs` locally and
watch the N+1 appear. That contrast is worth memorising for the "your endpoint is slow" question.

Also inspect the enum in psql:

```sql
\d orders
SELECT DISTINCT status FROM orders;
```

### Checkpoint questions

1. Why `values_callable`? What breaks without it during a rename?
2. Soft delete (`is_active`) vs hard delete — pros, cons, and how you keep referential integrity.
3. What is an audit log table, and why is `quantity_after` stored when it is derivable?
4. N+1 queries: cause, symptom in the log, three fixes.
5. Why `selectin` instead of `joinedload` here?

---

## Module 5 — Session and transaction boundary

**File:** `app/core/database.py`

### Concepts

- **Engine configuration** — `app/core/database.py:9`: `pool_size`, `max_overflow`,
  `pool_recycle`, and `pool_pre_ping=True`. `pool_recycle` closes connections before a proxy/firewall
  idle timeout kills them; `pool_pre_ping` makes the driver verify liveness before handing out a
  stale connection (one cheap round trip instead of a 500 on the first query).
- **`yield` dependency = transaction scope** — `get_session` at `app/core/database.py:30`:
  ```
  session = Session(engine)
  try:    yield session        # handler runs here
  except: rollback(); raise    # any exception -> nothing is persisted
  else:   commit()             # success -> one atomic write
  finally: close()
  ```
  This is the single most important design decision in the repo: **one request = one transaction**.
  Because the commit lives in the dependency, services never call `commit()` — they only `flush()`
  (see `app/repositories/product.py:115`, `app/repositories/user.py:70`).
- **`flush()` vs `commit()`** — `flush()` sends pending SQL to the DB inside the still-open
  transaction, which is why `order.id` is populated right after `self.orders.add(order)`
  (`app/services/order_service.py:94`) even though nothing is committed yet. `commit()` ends the
  transaction. Repositories use `flush()` + `refresh()` so the returned object has DB-generated
  values.
- **Why `refresh()`** — after `flush()` the in-memory object has no server defaults (e.g. the
  Postgres enum type). `refresh()` re-reads the row (`app/repositories/product.py:116`).
- **Test engine** — `null_engine` at `app/core/database.py:19` uses `NullPool`; note the tests
  currently use the pooled `engine`, which is exactly the gap flagged in Part 0.

### Exercise — prove atomicity with the test suite

```powershell
pytest tests/test_orders.py::TestOrderCreation::test_overselling_is_rejected_and_stock_untouched -v
```

Read the assertions (`tests/test_orders.py:48`): the response is 400 **and** product A's stock is
still 10. That second assertion is the interesting one — it proves the failed order left no
partial writes, which is only true because the exception unwound into `get_session`'s `except`
branch.

Second exercise, no server needed:

```python
# scratch.py — run with .\.venv\Scripts\python.exe scratch.py
from sqlmodel import Session
from app.core.database import engine
from app.models import User

with Session(engine) as s:                 # note: manual session = manual commit
    u = s.exec(__import__("sqlmodel").select(User).where(User.email == "ghost@example.com")).first()
    print("before:", u)
    s.add(User(email="ghost@example.com", full_name="Ghost"))
    s.flush()                               # visible to THIS session only
    print("after flush, still in tx:", s.get(User, 1) is not None)
    # no commit -> exiting the context manager rolls back
print("rolled back on exit (no commit called)")
```

### Checkpoint questions

1. Walk `get_session` line by line. What happens on a 404 raised inside a handler?
2. Why do services never call `commit()`?
3. `flush()` vs `commit()` vs `refresh()` — what does each do and when do you need it?
4. What breaks if two workers share one `Session`? (Answer: sessions are not thread-safe and must
   never cross a request boundary.)
5. Why is one-request-one-transaction a good default, and when would you break it?

---

## Module 6 — Repositories and SQL

**Files:** `app/repositories/product.py`, `app/repositories/order.py`, `app/repositories/user.py`

### Concepts

- **Repository = data access only.** No business rules, no HTTP. Its whole contract is
  "give me rows / persist this row". Rules live in services (`app/services/*`), which is what makes
  the rule set testable without HTTP and lets you swap SQLAlchemy for another backend.
- **`session.exec()` vs `session.execute()`** — SQLModel's `exec()` returns model instances;
  `execute()` returns raw SQLAlchemy rows. `health.py:19` uses `execute(text("SELECT 1"))` because it
  wants a scalar probe, not entities.
- **`col()`** — SQLModel requires `col(Product.sku)` (or `Product.sku` directly) inside `select()`
  to disambiguate columns from Python attributes; `repositories/product.py:19` shows the explicit form.
- **`selectin` loading** — see Module 4.
- **Row locking** — `get_many_for_update` at `app/repositories/product.py:22` builds
  `SELECT ... WHERE id IN (...) ORDER BY id FOR UPDATE`. The `ORDER BY` is not cosmetic: a consistent
  lock order is what prevents deadlocks when two transactions touch the same products in different
  orders. Module 10 goes deeper.
- **Pagination** — `list()` returns the page, `count()` returns the total, and the service combines
  them (`app/services/inventory_service.py:32`). Two queries, because `count(*) OVER ()` is not
  portable and window functions complicate some drivers.
- **Aggregates in SQL, not Python** — `total_inventory_value()` at
  `app/repositories/product.py:105` sums in Postgres and returns a `Decimal`, so you are not shipping
  10 000 rows to Python to add them up. `list_low_stock()` at `app/repositories/product.py:93` sorts
  by scarcity server-side.
- **`with_for_update` on a single row** — `get_for_update` at `app/repositories/order.py:17` locks
  the order header before a status transition, so two concurrent `PATCH /status` calls cannot both
  read `pending` and both apply `confirmed`.
- **`next_reference`** — `app/repositories/order.py:25` builds `ORD-000042` from `max(id) + 1`. It is
  readable and it is **not concurrency-safe** under load: two inserts in the same transaction window
  can collide on the unique index. Correct alternatives: a Postgres sequence, or a UUID/ULID.
  Saying this unprompted is a strong signal — see also Module 11 on migrations being the source of truth.

### Exercise

```powershell
$env:DB_ECHO = "True"; uvicorn app.main:app --reload
curl.exe "http://127.0.0.1:8000/api/v1/inventory/products?search=lap&low_stock=false&page=1&page_size=5"
```

Read the emitted SQL. You should see: a `count(*)` with the same `WHERE`, then the page query with
`LIMIT/OFFSET`. Note the `ILIKE`-style `lower(...) LIKE '%lap%'` from `repositories/product.py:48`.

Then in psql, check the indexes Alembic created and use `EXPLAIN ANALYZE`:

```sql
EXPLAIN ANALYZE SELECT * FROM products WHERE lower(name) LIKE '%laptop%';
```

Correct answer: **it will not use a btree index** — a leading wildcard defeats it. Real fix is a
trigram GIN index (`CREATE EXTENSION pg_trgm; CREATE INDEX ix_products_name_trgm ON products USING gin (name gin_trgm_ops);`)
or Elasticsearch. Knowing that `%foo%` is unindexable is the point of the exercise.

### Checkpoint questions

1. Why a repository layer at all? What does it buy you, and what does it cost?
2. `session.exec` vs `session.execute`.
3. `col()` and why SQLModel needs it.
4. Why is `max(id)+1` a bad reference generator? Give three alternatives.
5. When is `selectin` wrong, and what replaces it?

---

## Module 7 — Services and the order state machine

**Files:** `app/services/order_service.py`, `app/services/inventory_service.py`, `app/services/user_service.py`

This is where interviews are actually won, because these are the questions about *design*, not syntax.

### Concepts

- **Validate all, then mutate all.** `create_order` at `app/services/order_service.py:55` first
  validates *every* line (`app/services/order_service.py:71-85`) and only then writes anything
  (`:87` onwards). If line 3 is short on stock, lines 1–2 were never touched. The comment at
  `app/services/order_service.py:70` says so explicitly.
- **Lock before you validate.** `get_many_for_update` at `app/services/order_service.py:63` runs
  *before* the stock check, so the check and the decrement happen on the same locked snapshot. Check
  first, lock later would be a classic TOCTOU bug.
- **Guards on the entity** — the user must exist (`:56`) and be active (`:59`); products must exist
  (`:66`) and not be archived (`:73`). Each guard raises a domain error that becomes a status code.
- **Status machine enforcement** — `update_status` at `app/services/order_service.py:129`: same
  status → `ConflictError` (409, not 400); terminal status → `BusinessRuleError`; target not in
  `ALLOWED_STATUS_TRANSITIONS` → `BusinessRuleError` with a `details` payload naming the allowed
  values. That `details` dict is what makes the API debuggable for clients.
- **Cancel = restock** — `_restock_cancelled_order` at `app/services/order_service.py:174` re-locks
  the products (`:180`), adds each quantity back, and writes a movement per line. Cancellation is
  only legal before shipping, which the transition table enforces.
- **One audit path** — `InventoryService.adjust_stock` at `app/services/inventory_service.py:84` is
  documented as the "single entry point for changing stock so the audit log is never bypassed"
  (`:91`), and `_apply_stock_change` at `app/services/inventory_service.py:145` enforces
  `new_quantity >= 0`. Centralising the invariant is the entire design point.
- **Normalisation at the boundary** — emails lowercased (`app/services/user_service.py:35`), SKUs
  trimmed and uppercased (`app/services/inventory_service.py:45`). Do it once, on write, so every
  read can assume canonical form.
- **Referential rules as business rules** — `delete_user` at `app/services/user_service.py:66`
  refuses when open orders exist and tells you to deactivate instead (`:70`).

### Exercise — the six-step money trail

```powershell
# 1. user
curl.exe -X POST http://127.0.0.1:8000/api/v1/users -H "Content-Type: application/json" `
  -d '{"email":"dana@example.com","full_name":"Dana Reed"}'

# 2. product with opening stock (creates an INITIAL_STOCK movement)
curl.exe -X POST http://127.0.0.1:8000/api/v1/inventory/products -H "Content-Type: application/json" `
  -d '{"sku":"MOUSE-9","name":"Wireless Mouse","unit_price":"29.99","quantity_in_stock":40,"reorder_level":10}'

# 3. order 3 units at 8% tax -> stock 37
curl.exe -X POST http://127.0.0.1:8000/api/v1/orders -H "Content-Type: application/json" `
  -d '{"user_id":1,"tax_rate":"0.08","items":[{"product_id":1,"quantity":3}]}'

# 4. cancel -> stock back to 40, cancelled_at stamped
curl.exe -X POST "http://127.0.0.1:8000/api/v1/orders/1/cancel?reason=changed_mind"

# 5. audit trail
curl.exe http://127.0.0.1:8000/api/v1/inventory/products/1/movements

# 6. state machine refuses shipped -> cancelled
curl.exe -X PATCH http://127.0.0.1:8000/api/v1/orders/1/status -H "Content-Type: application/json" -d '{"status":"pending"}'
```

Then verify the invariants in SQL, which is the habit interviewers reward:

```sql
SELECT p.sku, p.quantity_in_stock,
       COALESCE(SUM(sm.quantity_change), 0) AS audit_delta
FROM products p LEFT JOIN stock_movements sm ON sm.product_id = p.id
GROUP BY p.sku, p.quantity_in_stock;
```

`quantity_in_stock` must equal the sum of every movement, always. If it ever does not, you have a
code path that bypassed `_apply_stock_change`.

### Checkpoint questions

1. Why validate every line before mutating any? (Answer: without it, a multi-line order can partially
   consume stock and then fail, and the client sees an error but the inventory moved.)
2. Why lock rows *before* checking stock?
3. Same-status → 409 but illegal-transition → 400. Defend the split.
4. How would you add a `refunded` status? Which files change? (Enums, transitions, migration,
   service branch, tests.)
5. Where should a stock-movement row be written, and what is the failure mode of writing it in the
   endpoint instead?

---

## Module 8 — Domain errors mapped to HTTP

**Files:** `app/core/exceptions.py`, `app/main.py:53`

### Concepts

- **Hierarchy with status codes as class attributes** — `AppError` at
  `app/core/exceptions.py:4` carries `status_code`, `code`, and `to_payload()`; subclasses override
  the first two (`NotFoundError` 404, `ConflictError` 409, `BusinessRuleError` 400,
  `ValidationError` 422, `InsufficientStockError` 400). Raising `BusinessRuleError(...)` from a
  service is all a service needs to know about HTTP.
- **One handler, many errors** — `@app.exception_handler(AppError)` at `app/main.py:54` catches the
  whole family. Register `AppError`, not each subclass.
- **Structured payload** — `{"code", "message", "details"}`. `code` is stable and machine-readable
  (clients branch on it), `message` is for humans, `details` carries context
  (`app/services/order_service.py:79`).
- **Third-party exception translation** — `@app.exception_handler(IntegrityError)` at
  `app/main.py:59` converts a Postgres unique-violation into a clean 409 instead of a 500 traceback.
- **Last-resort handler** — `@app.exception_handler(Exception)` at `app/main.py:70` logs with
  `logger.exception` and returns a generic 500. It must never leak `str(exc)` to the client.
- **Custom vs `HTTPException`** — use `HTTPException` for transport-level concerns (404 on a route,
  401, 403). Use domain exceptions when the *business rule* failed, because they keep the service
  layer framework-free and reusable from a CLI, a worker, or a WebSocket handler.

### Exercise

Produce every error shape in one pass:

```powershell
curl.exe http://127.0.0.1:8000/api/v1/users/999999                              # 404 not_found
curl.exe -X POST http://127.0.0.1:8000/api/v1/users -H "Content-Type: application/json" -d '{"email":"dana@example.com","full_name":"Dup"}'  # 409 conflict
curl.exe -X POST http://127.0.0.1:8000/api/v1/orders -H "Content-Type: application/json" -d '{"user_id":1,"items":[{"product_id":1,"quantity":9999}]}'          # 400 business_rule_violation
curl.exe -X POST http://127.0.0.1:8000/api/v1/orders -H "Content-Type: application/json" -d '{"user_id":1,"items":[]}'                                    # 422 validation_error
curl.exe -X DELETE http://127.0.0.1:8000/api/v1/users/1                                                                                          # 409 (open orders)
```

Then find the one path that produces 500: stop PostgreSQL and call
`/api/v1/health/ready`. Confirm the response is a generic `internal_error` while the *log* has the
full traceback. That separation — generic to the client, verbose in the log — is the pattern.

### Checkpoint questions

1. Custom exceptions vs `HTTPException`: when does each belong?
2. Why 409 for a duplicate email rather than 400 or 422?
3. What must an exception handler never do? (Leak internals, swallow tracebacks, or commit work.)
4. How do you add a new error type end-to-end?
5. Why does the `Exception` handler not catch `HTTPException`? (FastAPI installs its own, more
   specific handler first.)

---

## Module 9 — Money, Decimal, and quantisation

**Files:** `app/services/order_service.py:23`, `app/models/order.py:34`, `app/models/product.py:20`

### Concepts

- **`Decimal`, never `float`** — binary floats cannot represent `0.1`; `0.1 + 0.2 != 0.3`. Money in
  a float column eventually fails an audit. `unit_price`, `subtotal`, `tax_amount`, `total_amount`,
  and `line_total` are all `Decimal` backed by `Numeric(precision, scale)`.
- **Fixed scale** — `max_digits=14, decimal_places=2` (`app/models/order.py:34`) maps to
  `NUMERIC(14,2)` in Postgres, which does the rounding for you at the storage layer.
- **Explicit rounding** — `money()` at `app/services/order_service.py:26` quantises to `0.01` with
  `ROUND_HALF_UP` (banker's rounding would surprise a customer; the codebase picks the commercial
  convention and states it).
- **`Decimal(str(value))`** — the `str` bridge avoids inheriting float error when a value arrives as
  JSON number or float. This one detail is what interviewers probe.
- **Totals from rounded lines** — `line_total` is rounded per line, then summed; the sum is rounded
  again (`app/services/order_service.py:100`, `:123`). Rounding once at the end vs per line gives
  different cents; decide and document which you do.
- **Serialization** — Pydantic emits `Decimal` as a JSON **string** (`"34.65"`), which is deliberate:
  a JSON number would be re-parsed as a float by many clients. `tests/test_orders.py:27` asserts on
  the string form.

### Exercise

```python
# money.py — .\.venv\Scripts\python.exe money.py
from decimal import Decimal, ROUND_HALF_UP
from app.services.order_service import money

print(money(Decimal("10.005")))          # 10.01  (half-up)
print(money(Decimal("10.004")))          # 10.00
print(money(Decimal("0.1") + Decimal("0.2")))        # 0.30  (exact)
print(money(0.1 + 0.2))                  # 0.30  (str() rescues the float)
print(money(Decimal("2.675")))           # 2.68  (float would give 2.67)
print(float(Decimal("0.1")) + float(Decimal("0.2"))) # 0.30000000000000004 — why we avoid float
```

### Checkpoint questions

1. Why not `float`? What exactly goes wrong?
2. `ROUND_HALF_UP` vs banker's rounding — which would you pick for invoices and why?
3. Round per line or at the end? What is the difference in cents, and which do you pick?
4. Why does Pydantic serialise `Decimal` as a string?
5. Where does rounding belong: application, ORM, or database column type?

---

## Module 10 — Concurrency: locking and oversell

**Files:** `app/repositories/product.py:22`, `app/repositories/order.py:17`, `app/services/order_service.py:63`

### Concepts

- **The lost-update / oversell problem.** Without a lock, two transactions both read
  `quantity_in_stock = 1`, both decide they can sell it, both write `0`, and one physical item has
  been sold twice. Validation alone does not help; the read and the write must be atomic.
- **`SELECT ... FOR UPDATE`** — row-level exclusive lock held until the transaction ends.
  `get_many_for_update` (`app/repositories/product.py:22`) locks *only the rows involved*, so
  concurrent orders for different products never block each other.
- **Pessimistic vs optimistic.** This repo is pessimistic (lock first). Optimistic locking is a
  `version_id` column plus `UPDATE ... WHERE version = :seen` and a retry on 0 rows updated —
  cheaper when contention is rare, and it needs no long-lived locks.
- **Lock ordering prevents deadlock.** `.order_by(Product.id)` at `app/repositories/product.py:30`
  makes every transaction acquire locks in the same order. Two orders touching {A,B} and {B,A}
  would otherwise deadlock; ordering turns that into a wait.
- **The lock is held until commit**, which is why `get_many_for_update` must be called before the
  validation loop and why the transaction must be short.
- **Lost update in the ORM** — SQLAlchemy's unit of work only issues `UPDATE` for columns it thinks
  changed; a concurrent process's write to the same column is simply overwritten. `FOR UPDATE`
  closes that window; a `version_id` column detects it.

### Exercise — prove it, do not just believe it

Create a product with exactly 1 unit, then fire 5 concurrent orders:

```python
# race.py — .\.venv\Scripts\python.exe race.py   (server must be running)
import concurrent.futures, httpx

BASE = "http://127.0.0.1:8000/api/v1"

def make_product():
    r = httpx.post(f"{BASE}/inventory/products", json={
        "sku": "RACE-1", "name": "Last One", "unit_price": "9.99",
        "quantity_in_stock": 1, "reorder_level": 0})
    return r.json()["id"]

def order(pid, user_id, i):
    r = httpx.post(f"{BASE}/orders", json={"user_id": user_id,
                   "items": [{"product_id": pid, "quantity": 1}]})
    return i, r.status_code, r.json().get("code")

pid = make_product()
users = [httpx.post(f"{BASE}/users", json={"email": f"r{i}@x.com", "full_name": f"R{i}"}).json()["id"]
         for i in range(5)]

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    for result in pool.map(lambda t: order(pid, t[1], t[0]), list(enumerate(users))):
        print(result)

stock = httpx.get(f"{BASE}/inventory/products/{pid}").json()["quantity_in_stock"]
movements = httpx.get(f"{BASE}/inventory/products/{pid}/movements").json()["total"]
print("final stock:", stock, "| movements:", movements)
```

Expected: exactly one `201`, four `400`s, final stock `0`, and **one** `sale` movement. If two
requests succeed, you have an oversell bug and you just found it with a 20-line script.

Second demo, the raw locking behaviour, in two psql sessions:

```sql
-- session A
BEGIN;
SELECT id, quantity_in_stock FROM products WHERE id = 1 FOR UPDATE;   -- holds the lock

-- session B (blocks until A commits)
BEGIN;
SELECT id, quantity_in_stock FROM products WHERE id = 1 FOR UPDATE;   -- hangs here
```

### Checkpoint questions

1. Explain the oversell race precisely, then the two fixes (lock vs version column).
2. Why `ORDER BY id` before `FOR UPDATE`?
3. When can a deadlock still happen here, and how would you detect it in production?
4. What is isolation level READ COMMITTED doing for you here, and what does SERIALIZABLE change?
5. How long should a transaction be, and what happens to throughput if it holds locks for 2 seconds?

---

## Module 11 — Migrations with Alembic

**Files:** `alembic.ini`, `alembic/env.py`, `alembic/versions/f5e85f10ac53_initial_schema.py`

### Concepts

- **Migrations are the source of truth.** `README.md:219` says it explicitly: never
  `create_db_and_tables()` in production (that helper exists at `app/core/database.py:26` but is
  never called — good, and it is Module 13 material too).
- **Metadata wiring** — `alembic/env.py:7` imports `app.models` purely for its side effect:
  every table must be registered on `SQLModel.metadata` before autogenerate can diff. Forget the
  import and Alembic cheerfully generates a migration that drops tables.
- **URL from settings** — `alembic/env.py:11` injects `settings.database_url`, so migrations and the
  app can never disagree about the database.
- **Autogenerate is a draft** — `alembic/versions/f5e85f10ac53_initial_schema.py:21` was generated
  and then reviewed. Notice it correctly captured `sa.Numeric(precision=12, scale=2)` (`:30`) and the
  lowercase enum values (`:59`) — proof that the model definitions are the true schema.
- **Online vs offline** — `run_migrations_online` (`:31`) uses `NullPool` (migrations must not hold
  pooled connections); `run_migrations_offline` (`:19`) emits SQL to stdout for a DBA-run deploy.
- **`compare_type=True`** — catches column type changes, which autogenerate otherwise misses.
- **expand/contract** — the safe way to change a live schema: add nullable column → deploy code
  that writes both → backfill → switch reads → drop the old column. Migrations that rename or drop
  columns are single-step outages.

### Exercise

```powershell
alembic current
alembic history --verbose
alembic revision --autogenerate -m "add product barcode"
alembic upgrade head
alembic downgrade -1
```

Then read the generated file before trusting it, and delete the scratch migration. One classic trap
to look for: Alembic cannot detect a column rename (it emits drop + add, losing data) and it does
not detect table renames at all.

```sql
SELECT version_num FROM alembic_version;
SELECT * FROM alembic_version;
```

### Checkpoint questions

1. Why not `Base.metadata.create_all()` on startup?
2. What breaks if `env.py` forgets `import app.models`?
3. What is expand/contract and why is it needed?
4. How do you rename a column with zero downtime?
5. When would you hand-write a migration instead of autogenerating?

---

## Module 12 — Testing strategy

**Files:** `tests/conftest.py`, `tests/test_health.py`, `tests/test_orders.py`, `tests/test_users_inventory.py`, `pytest.ini`

### Concepts

- **`TestClient` is the real app in-process** — `tests/conftest.py:13` uses `with TestClient(app)`,
  which triggers the lifespan. Requests go through the whole stack: routing, DI, validation,
  services, repositories, Postgres. FastAPI 0.142 prefers `httpx`-based clients; this repo pins
  `httpx==0.28.1` in `requirements.txt`.
- **Fixtures as a scenario DSL** — `user` (`tests/conftest.py:35`) and `products`
  (`tests/conftest.py:50`) create realistic data through the *public API*, so tests never bypass
  validation. The three products are deliberately different: 10 in stock / reorder 3 (healthy),
  2 / 5 (low), 0 / 2 (out). Every inventory test picks the right one by that design.
- **Isolation** — `clean_db` (`tests/conftest.py:19`) truncates before *and* after each test,
  deleting children first (`StockMovement`, `OrderItem`, `Order`, `Product`, `User`) to respect
  foreign keys. Correct order, blunt instrument: one test failing mid-way can leak rows into the
  next test.
- **Unique data per test** — `uuid.uuid4().hex` in the fixture emails/SKUs
  (`tests/conftest.py:36`) so accidental leftovers cannot cause a 409.
- **Business rules are the tests** — `tests/test_orders.py` asserts on outcomes, not on calls:
  exact money strings (`:27-29`), stock after ordering (`:34`), stock *unchanged* after a rejected
  order (`:63`), the state machine (`:115`, `:125`), cancel restoring stock (`:144`), the audit log
  after cancellation (`:175`), and referential protection on delete (`:206`).
- **The schema is also tested** — `tests/test_health.py:16` fetches `/openapi.json` and asserts the
  title and that `/api/v1/orders` is present. A CI-friendly guard against accidental route removal.
- **`pytest.ini`** sets `testpaths`, `--strict-markers`, and suppresses `DeprecationWarning`. Add
  `--strict-config` and a coverage floor (`pytest-cov`) when you care.

### Exercise

```powershell
pytest -v                                   # 37 tests
pytest tests/test_orders.py -k status -v    # the state machine only
pytest -x -q                                # stop at first failure
pytest --collect-only -q                    # what would run
```

Then run the failing-test loop properly:

```powershell
# break it on purpose: comment out the stock check at order_service.py:75-85, re-run, observe
pytest tests/test_orders.py::TestOrderCreation::test_overselling_is_rejected_and_stock_untouched -v
# restore the code and confirm green again
```

That loop — mutate, watch red, restore, watch green — is how you learn to *read* a test suite.

Then note the improvement you would make in a real project: override the session dependency with a
transaction that always rolls back, so each test is isolated *and* leaves no residue:

```python
# tests/conftest.py sketch — the standard pattern
@pytest.fixture
def db_session():
    with Session(engine) as session:
        yield session
        session.rollback()

app.dependency_overrides[get_session] = lambda: db_session
```

### Checkpoint questions

1. `TestClient` vs `httpx.AsyncClient` vs calling services directly — when each?
2. Fixture scope, and why `clean_db` is function-scoped.
3. How do you test a business rule without touching HTTP? (Here: services accept a `Session`, so you
   can instantiate them directly with a test session.)
4. `dependency_overrides` — what is it for, and what must you remember to undo?
5. How do you test a race condition deterministically? (You cannot fully; you test the invariant
   with locks/constraints, and stress it in a separate job.)

---

## Module 13 — Dead code and design critique

Every item below was verified by searching the repo. Being able to *find* these is worth more in an
interview than memorising them — it shows you read the code rather than skimmed it.

| Finding | Where | Interpretation |
|---|---|---|
| `count_stmt` built, filtered, then never used | `app/repositories/user.py:30,39,43`, `app/repositories/product.py:45,54,58,63`, `app/repositories/order.py:39,43,47` | The `count()` methods rebuild the same filters. Dead assignment today, but a trap: fix `count()` and forget `count_stmt` and the two silently diverge. |
| `_decrement_stock_for_order`, `_restore_stock_for_order`, `to_decimal` never called | `app/services/inventory_service.py:173,188,203` | `OrderService` builds its own movements (`:195`, `:207`), so the *intent* of "one entry point" (`app/services/inventory_service.py:91`) is not actually achieved across services. The real fix: move `_apply_stock_change` into a shared unit or have `OrderService` call `InventoryService.adjust_stock`. |
| `InsufficientStockError` defined, never raised | `app/core/exceptions.py:42` | Dead branch; `BusinessRuleError` is used instead. |
| `ValidationError` defined, never raised | `app/core/exceptions.py:32` | 422s come from Pydantic, so the app-level 422 is unreachable. |
| `PaginationParams` vs `Pagination` | `app/schemas/common.py:29` vs `app/api/deps.py:13` | Two pagination models with different sources of truth (`le=100` hardcoded vs `MAX_PAGE_SIZE`). Pick one. |
| `Product.is_low_stock` on the model, never used | `app/models/product.py:34` | The API value comes from the schema's `@computed_field` (`app/schemas/product.py:48`). Duplicated logic, two places to forget. |
| `Order.item_count` never used | `app/models/order.py:55` | Could be a `@computed_field` on `OrderRead`. |
| `Message` schema never used | `app/schemas/common.py:12` | Leftover from a deleted `/health` text response. |
| `create_db_and_tables`, `null_engine` never used | `app/core/database.py:26,19` | `null_engine` is presumably intended for tests/scripts; the tests use the pooled engine instead. |
| `get_by_reference`, `user_exists` never used | `app/repositories/order.py:21,80` | `user_exists` is redundant — `UserRepository.get` already answers it. |
| `next_reference` is racy | `app/repositories/order.py:25` | `max(id)+1` collides under concurrency. Sequence or ULID. |
| Count/page filter logic duplicated 3× | all repositories | Prime candidate for a small query-builder helper. |
| Tests truncate the live database | `tests/conftest.py:19-31` | Point `POSTGRES_DB` at a scratch DB; better, wrap each test in a rolled-back transaction. |
| `stock_movements` relationship declared, never traversed | `app/models/product.py:28` | Movements are queried explicitly instead; the relationship is unused. |

### Checkpoint questions

1. Which of these would you delete in a first PR, and which would you keep?
2. `OrderService` writing `stock_movements` directly vs calling `InventoryService` — how do you feel
   about coupling an order to an inventory module, and what is the alternative?
3. How would you prove the "one entry point for stock changes" invariant holds forever?
   (Answer: make `quantity_in_stock` a private column and expose only a method that writes the
   movement — language-level enforcement rather than convention.)
4. What is the risk in `count_stmt` being dead, concretely?

---

## Part 2 — Interview question bank

Each answer is what you should say in 60 seconds, plus where in this repo you can prove it.
Answers marked **[gap]** are intentionally not implemented here — see Part 3.

### Fundamentals

**1. What is FastAPI, and what is it built on?**
Starlette for the ASGI layer, Pydantic v2 for validation and serialisation, Uvicorn as the ASGI
server. It is type-hint driven: the same annotations drive validation, dependency injection,
serialisation, and the OpenAPI schema, so there is one declaration instead of four.
*Proof:* `app/main.py:28`, `/openapi.json` generated from the annotations in `app/api/v1/endpoints/*`.

**2. ASGI vs WSGI?**
WSGI is synchronous, one request per worker thread, and frameworks like Flask block on I/O. ASGI is
async and event-loop based, so one process can hold many concurrent connections that are waiting on
the database. FastAPI supports both: `async def` endpoints run on the loop, `def` endpoints run in a
threadpool. *Proof:* every handler here is sync `def` (`app/api/v1/endpoints/orders.py:35`) precisely
because the DB layer is the blocking psycopg driver.

**3. `def` vs `async def` endpoints?**
`async def` for I/O you await (an async HTTP or DB driver). Plain `def` for blocking work — FastAPI
runs it in a threadpool so the event loop is not blocked. Using `def` with an async client, or
`async def` with blocking calls, is the two classic mistakes. *Proof:* sync handlers throughout
`app/api/v1/endpoints/*`, blocking `Session` in `app/core/database.py:30`.

**4. Path vs Query vs Body parameters?**
Path params are part of the URL (`/users/{user_id}`) and are required. Query params come after `?`
and are for filters, pagination, and flags. Body params are JSON and used for create/update. FastAPI
infers this from the default value: no default → path/body, scalar default → query. `Annotated`
plus `Path`/`Query`/`Body` makes it explicit. *Proof:* `app/api/v1/endpoints/orders.py:42` (`Path(ge=1)`),
`:17` (`Query(alias="status")`), `:35` (`payload: OrderCreate` → body).

**5. What does `response_model` do?**
Declares the output contract: it filters fields out of the response, validates the shape, generates
the OpenAPI schema, and is what makes returning an ORM object safe. Prefer it over a bare return
annotation when you want the response filtered. *Proof:* `response_model=Page[OrderRead]`
(`app/api/v1/endpoints/orders.py:13`) and `ORMModel.from_attributes`
(`app/schemas/common.py:8`).

**6. Status codes you use and why?**
200 read/update, 201 created (with `Location` ideally), 204 delete with empty body, 400 business rule
violation, 401 unauthenticated, 403 unauthorised, 404 missing, 409 conflict/duplicate/illegal state
change, 422 schema validation. *Proof:* 201 at `app/api/v1/endpoints/users.py:29`, 204 at `:64` (with an
explicit empty `Response`), 409 from `app/core/exceptions.py:27`, 422 straight from Pydantic.

**7. How does validation error handling work?**
FastAPI validates path, query, header, cookie, and body params against the annotations before the
handler runs; failures become a 422 with a list of `{loc, msg, type}` entries. Customise the shape
with an `RequestValidationError` handler. *Proof:* `tests/test_orders.py:79` (duplicate lines → 422)
and `:94` (empty items → 422).

**8. What are the auto docs?**
`/docs` (Swagger UI), `/redoc`, and `/openapi.json`, generated from your annotations. `summary=`,
`tags=`, and `response_model` are what make them useful. You can override them per app
(`app/main.py:33`). *Proof:* `tests/test_health.py:16` asserts the OpenAPI schema contains the title
and the orders path.

**9. Middleware vs dependencies?**
Middleware wraps the entire request/response cycle and is invisible to your handlers — use it for
CORS, timing, request IDs, auth tokens, and rate limits. Dependencies are per-endpoint, visible in
the signature, cacheable and overridable in tests — use them for sessions, pagination, and
services. *Proof:* CORS as middleware (`app/main.py:39`), session as a dependency
(`app/api/deps.py:10`).

**10. What is `yield` vs `return` in a dependency?**
`yield` dependencies are generator functions: FastAPI runs code up to `yield`, injects the value, and
then resumes the generator after the response to run cleanup — commit/rollback/close, cache release,
token cleanup. `return` dependencies cannot clean up. *Proof:* `get_session`
(`app/core/database.py:30`) is the canonical example, and teardown ordering is why an exception in the
handler still triggers rollback.

**11. `Depends` vs `Security`?**
`Security` is `Depends` plus the ability to declare scopes and it integrates with
`OAuth2PasswordBearer`/`APIKeyHeader` for OpenAPI security definitions. Use `Security` on auth
dependencies, `Depends` for everything else. **[gap]** — no auth here (`README.md:215`).

**12. Background tasks?** FastAPI runs a `BackgroundTask` after the response is sent, in the same
process, for short follow-ups (email, webhook, cache write). Long jobs belong to Celery/RQ/arq; the
task dies with the worker otherwise. **[gap]**

### Application design

**13. How do you structure a FastAPI project for a team?**
By change-coupling, not by technical type. Here: `api` (HTTP shape, DI), `schemas` (wire contract),
`models` (persistence), `repositories` (data access), `services` (business rules), `core` (config,
session, errors). Strictly one-directional: endpoints → services → repositories → models
(`README.md:50`). *Proof:* read any request end-to-end and you never skip a layer.

**14. `APIRouter` and versioning?**
A router is a mini-app: its own prefix, tags, dependencies, and responses. Nest them — one per
domain, one aggregate, then `include_router` per version with a prefix, so v1 and v2 can coexist
while sharing services. *Proof:* `app/api/v1/router.py:5`, mounted at `app/main.py:47`.

**15. Why an app factory?** Configuration per instance, no import-time side effects, tests that build
an app with overridden settings, and the ability to serve several apps in one process.
*Proof:* `create_app()` (`app/main.py:28`) and `app = create_app()` (`:79`).

**16. What is lifespan for?** Startup/shutdown work tied to the app's lifetime: connection pools,
HTTP clients, cache warm-up, and — critically — *not* schema creation in production.
*Proof:* `app/main.py:21`.

**17. Settings management?** `pydantic-settings` gives typed, validated, env-driven config with `.env`
fallback, and one place that derives the DSN (`app/core/config.py:38`). Env vars beat `.env`, so
secrets never need to be committed. `@lru_cache` (`:47`) parses once. *Proof:* the whole of
`app/core/config.py`.

**18. Custom exceptions vs `HTTPException`?** Transport concerns (401/403/404-route) →
`HTTPException`. Business rule failures → domain exceptions, so the service layer stays free of HTTP
and remains reusable from a CLI, a Celery task, or a WebSocket. *Proof:* `app/core/exceptions.py`
plus the three handlers at `app/main.py:53`.

**19. SQLModel vs plain SQLAlchemy vs plain Pydantic?**
SQLModel merges table and schema in one class — less boilerplate, faster prototyping. Plain
SQLAlchemy is more explicit and better for complex mappings. This repo still separates
models and schemas because the two concerns genuinely differ. *Proof:* `app/models/*` vs `app/schemas/*`.

### Data, validation, SQL

**20. `Decimal` vs `float`?** Floats are binary approximations; `0.1 + 0.2 != 0.3`, and errors
compound across calculations and comparisons. Use `Decimal` plus a fixed-scale DB column
(`NUMERIC(14,2)`), and quantise explicitly with `ROUND_HALF_UP`. *Proof:*
`app/services/order_service.py:26`, `app/models/order.py:34`, `tests/test_orders.py:27`.

**21. How do you store enums in Postgres?** As a native enum type with the *values* you control,
using `values_callable` so member renames do not corrupt stored data. Alternatively a lookup table or
a `CHECK`-constrained varchar when you need to add values without a migration.
*Proof:* `app/models/order.py:17`, visible as `sa.Enum('pending', ...)` in
`alembic/versions/f5e85f10ac53_initial_schema.py:59`.

**22. `model_validator` vs `field_validator`?** Field-level single-value checks
(`field_validator`), and `model_validator(mode="after")` for cross-field rules like "no duplicate
product ids in one order". *Proof:* `app/schemas/order.py:34`.

**23. How do you implement PATCH?** `model_dump(exclude_unset=True)` so only provided fields are
applied, plus a conflict check on whatever unique fields are changing. *Proof:*
`app/services/user_service.py:48`, `app/services/inventory_service.py:71`.

**24. N+1 queries?** Serialising a list of parents with lazy children emits one child query per
parent. Detect it in the log with `DB_ECHO`, fix with `selectin`/`joinedload`, `joinedload` +
`contains_eager`, or an explicit `selectinload` in the repository. *Proof:* `lazy="selectin"` at
`app/models/order.py:48`, `app/models/user.py:20`.

**25. Pagination approaches?** `OFFSET/LIMIT` is simple but degrades on deep pages and can
duplicate/skip rows under concurrent writes; keyset (`WHERE id < last_seen_id ORDER BY id DESC LIMIT n`)
is stable and fast for infinite scroll but has no cheap `total`. This repo returns both `items` and
`total` (`app/schemas/common.py:16`), accepting the count cost. *Proof:*
`app/repositories/product.py:35`.

**26. App-level validation or DB constraints?** Both. Constraints are the last line of truth
(`NOT NULL`, `UNIQUE`, `CHECK (quantity >= 0)`, FKs) and protect against every writer including
scripts and migrations. App-level validation gives good error messages. This repo relies on app
checks plus the unique index, and converts the resulting `IntegrityError` into a 409 at the edge
(`app/main.py:59`) — *that* is the correct division of labour. *Proof:* the unique index on
`users.email` in the migration, mapped to 409 by `app/main.py:59`.

**27. Soft delete vs hard delete?** Soft delete keeps history and avoids FK breakage but needs every
query to filter, complicates uniqueness, and grows the table. Hard delete is honest; use it when
nothing references the row, or cascade deliberately. Here: soft delete via `is_active` for users
(`app/api/v1/endpoints/users.py:52`) and hard delete blocked when open orders exist
(`app/services/user_service.py:66`). *Proof:* both.

### Transactions, concurrency, operations

**28. How do you handle database transactions in FastAPI?**
One transaction per request via a `yield` dependency that commits on success and rolls back on any
exception (`app/core/database.py:30`). The consequence: services call `flush()` to obtain generated
IDs but never `commit()`, so there is exactly one commit point and no partial failure.
*Proof:* `get_session`, `app/repositories/product.py:115`.

**29. `flush` vs `commit` vs `refresh`?** `flush` pushes pending changes inside the open transaction
(you get the PK); `commit` ends it; `refresh` re-reads the row so server defaults and DB types are
populated. *Proof:* `add()` = add + flush + refresh (`app/repositories/product.py:113`).

**30. How do you prevent overselling?** Check-then-act is not atomic. Lock the rows
(`SELECT ... FOR UPDATE`) *before* validating, hold the lock through the write, and always acquire in
a deterministic order to avoid deadlock. Alternatives: a `CHECK (quantity_in_stock >= 0)` constraint
as a backstop, optimistic `version_id` with retry, or serialisable isolation. *Proof:*
`app/repositories/product.py:22`, `app/services/order_service.py:63`, and the race script in Module 10.

**31. Pessimistic vs optimistic locking?** Pessimistic locks rows up front (predictable, blocks
others). Optimistic lets everyone read, and detects the conflict at write time with a version column
and a retry loop (no blocking, wasted work on conflict). Choose by contention: reads mostly → version
column; hot rows → `FOR UPDATE`. *Proof:* the repo uses pessimistic only.

**32. Idempotency?** Retries and double-clicks cause duplicate orders. Accept an `Idempotency-Key`
header, store `(key, user, response)` with a unique index, and replay the stored response on a repeat.
Related: make writes naturally idempotent, and support `POST .../cancel` being called twice — this
repo answers the second cancel with 409 (`tests/test_orders.py:169`). **[gap]** for key storage.

**33. Why Alembic over `create_all`?** `create_all` never alters an existing table, cannot drop or
backfill, and gives you no history. Alembic produces an ordered, reviewable, reversible script per
change, and `alembic_version` records what is deployed. *Proof:* `alembic/env.py`,
`alembic/versions/f5e85f10ac53_initial_schema.py`.

**34. Connection pooling?** `pool_size` (kept-open connections), `max_overflow` (burst allowance),
`pool_recycle` (avoid proxies dropping idle connections), `pool_pre_ping` (detect dead connections
cheaply). Size `pool_size × workers` under your Postgres `max_connections`. *Proof:*
`app/core/database.py:9-16`.

**35. Caching strategy?** HTTP-level (`Cache-Control`, ETag) for public reads, Redis for expensive
computed data, and a short TTL on anything a write invalidates. Cache-aside with explicit
invalidation on write; never cache per-user responses in a shared key. **[gap]**

**36. How do you debug a slow endpoint?** Turn on `DB_ECHO`, count queries per request (N+1?),
`EXPLAIN ANALYZE` the slow statement, look for missing indexes and `%LIKE%` scans, check pool
saturation and `pool_timeout`, then add the index or eager load. Prove it before and after with a
measurement. *Proof:* the `%search%` pattern at `app/repositories/product.py:48` is a real example
that a btree cannot serve.

**37. Rate limiting?** Token bucket or sliding window in Redis, keyed by user or IP, enforced in
middleware so it applies to every route, returning 429 with `Retry-After`. Fail open or closed
deliberately. **[gap]** — spec in Part 3.

**38. Observability?** Structured logs with a request ID propagated from middleware, plus metrics
(latency percentiles, error rate, pool saturation) and traces across the request. Health endpoints
for probes. Log the exception, return a generic message. *Proof:* logging setup at
`app/main.py:14`, generic 500 at `:70`, probes at `endpoints/health.py`.

**39. How do you deploy?** Containerise (multi-stage Dockerfile, non-root user, `uvicorn` with
N workers), run migrations as a release step *before* the new pods serve traffic, keep
`DEBUG=False`, and drive config from env vars. Scale horizontally since the app is stateless.
*Proof:* `requirements.txt` pins exact versions for reproducible builds; `README.md:219`.

**40. Testing strategy?** Unit-test services with an injected session, integration-test endpoints
with `TestClient` against a real (scratch) database, and keep the suite fast enough to run on every
save. Assert on behaviour and money, not on internals. *Proof:* `tests/` (37 tests),
`tests/test_orders.py:48` for the partial-failure assertion.

---

## Part 3 — Build specs (no code provided)

Each task is a gap this repo intentionally leaves open. Implement it yourself, then answer the
attached question out loud — that is the interview.

### Task 1 — JWT authentication

**Goal:** `Authorization: Bearer <token>`; users table gains a password hash.

1. Add `hashed_password` to `User`; add `POST /api/v1/auth/register` and `/auth/login` (verify with
   `pwdlib`/`passlib` + `argon2` or `bcrypt` — never store plaintext, never roll your own KDF).
2. Add `get_current_user` in `app/api/deps.py` using `OAuth2PasswordBearer` + `jwt`/`pyjwt`, raising
   401 with `WWW-Authenticate: Bearer`.
3. Guard `orders` and `inventory` routers with `Security(...)`; make `POST /orders` read
   `user_id` from the token, not the body.
4. Tests: 401 without a token, 401 with a bad/expired token, 201 with a valid token, and a user may
   not read another user's orders.
5. Add rate limiting to `/auth/login` (Task 3).

**Interview questions:** why hash passwords rather than encrypt? Where does the token live and why
is it not a cookie by default? What are refresh tokens and what problem do they solve? How do you
revoke a token before expiry?

### Task 2 — Custom middleware

**Goal:** request ID + timing + access log.

1. `@app.middleware("http")` in `app/main.py`: read or generate `X-Request-ID`, bind it to
   `logging`, time the call, log method/path/status/duration, set the header on the response.
2. Emit an access log line per request in the existing format at `app/main.py:16`.
3. Add a `pytest` fixture-free assertion in `tests/test_health.py` that the header is present.

**Interview questions:** why middleware rather than a dependency (applies to every route including
404s and static)? What is the ordering of multiple middleware? Where do you put exception handling
relative to it?

### Task 3 — Sliding-window rate limiter

**Goal:** 429 with `Retry-After`.

1. Redis-backed sliding window keyed by API key/user/IP; middleware-enforced.
2. Configurable limit/window via `app/core/config.py`; override the store in tests with
   `app.dependency_overrides` or a fake.
3. `Retry-After` header and a JSON error matching the `AppError` payload shape.
4. Tests: under limit passes, over limit 429, window slides, different keys are independent.

**Interview questions:** token bucket vs sliding window? Per-user vs per-IP and why both? Fail open
or closed when Redis is down? Why store the window in Redis and not in process memory?

### Task 4 — WebSocket stock channel

**Goal:** live low-stock notifications.

1. `@app.websocket("/ws/inventory")` with a connection manager holding `WebSocket` objects per
   product id.
2. Broadcast from the stock-change path in `InventoryService._apply_stock_change`
   (`app/services/inventory_service.py:145`) — this is where you realise the "single entry point"
   design pays off.
3. Tests with `TestClient.websocket_connect`; make the broadcaster a dependency so tests can stub it.

**Interview questions:** how does this differ from SSE and long polling? What happens to your
connections when you scale to 4 workers (you need Redis pub/sub)? How do you authenticate a
WebSocket?

### Task 5 — Containerise

1. Multi-stage `Dockerfile`: builder installs into a virtualenv, final stage copies it onto
   `python:3.13-slim`, non-root user, `HEALTHCHECK` hitting `/api/v1/health/ready`.
2. `docker-compose.yml`: `api` (2+ workers) + `db` (postgres:16, healthcheck, volume).
3. Migrations run as an entrypoint step or a one-shot compose service, not on every worker start.

**Interview questions:** why not run migrations on app startup? What breaks with multiple replicas?
How do you pass secrets? How do you keep the image small?

### Task 6 — Response caching

1. ETag/`If-None-Match` 304 for `GET /inventory/products/{id}` and `/orders/{id}` (hash the
   serialised body, or use the `updated_at` you already have).
2. Redis cache-aside for `GET /inventory/summary`, invalidated on any stock change.
3. Tests asserting a 304 on the second call and a 200 after a write.

**Interview questions:** why is this endpoint still correct with ETags? What invalidation strategy
for the summary? Why not cache at the HTTP layer with a CDN for authenticated routes?

### Task 7 — Async everything

1. `asyncpg` + `create_async_engine`, `AsyncSession`, `get_session` becomes an async generator
   dependency, services become `async def`.
2. Endpoints become `async def`; confirm with a blocking-sleep benchmark that the event loop is
   actually free.
3. `httpx.AsyncClient` tests with `pytest-asyncio`.

**Interview questions:** what is still blocking in an async FastAPI (sync DB drivers, CPU work)?
Where would you offload with `run_in_threadpool`? How does connection pooling differ from
`psycopg`'s pool, and why do async pools exist at all?

---

## Part 4 — Mastery checklist

### Self-check (say each aloud, no notes)

- [ ] Draw the layer graph and explain why the dependency direction is one-way.
- [ ] Explain `yield` dependencies and name the commit point.
- [ ] Explain `Decimal` money handling end to end, including rounding.
- [ ] Explain the oversell race, the fix, and the deadlock it introduces.
- [ ] Explain `Annotated` dependency aliases and why they beat `= Depends()`.
- [ ] Explain `response_model`, `from_attributes`, and `exclude_unset`.
- [ ] Explain Alembic vs `create_all`, and expand/contract.
- [ ] Explain `pool_pre_ping`, `pool_recycle`, and pool sizing.
- [ ] Explain `SELECT ... FOR UPDATE` and `ORDER BY id`.
- [ ] Explain the difference between `flush` and `commit`.
- [ ] Explain when you would *not* use a repository layer.
- [ ] Explain the `count_stmt` dead code and its risk.

### Whiteboard drills

1. **Design a new endpoint from scratch on a whiteboard:** `POST /api/v1/orders/{id}/refund`.
   Specify the schema, the service method, the transition-table change, the migration, and three
   tests. (Answers: `OrderStatus.REFUNDED` + transitions; restock only for a shipped/delivered order;
   a `REFUND` movement type; migration adding the enum value; tests for legal transition, illegal
   transition, and stock restored.)
2. **Find the bug:** given a version of `create_order` that decrements stock inside the validation
   loop, explain the failure mode and the fix. Then explain what test proves it
   (`tests/test_orders.py:63`).
3. **Diagnose:** an endpoint returns 500 only under load in production but works locally. Candidate
   causes: pool exhaustion (`pool_size × workers` vs `max_connections`), connection dropped by a
   proxy (`pool_pre_ping`/`pool_recycle`), enum value mismatch between environments, or a race in
   `next_reference`. How would you prove each?
4. **Scale it:** how does the design change for 10 engineers? Code ownership per layer, contract
   tests on schemas, feature flags, and separate deployable services only where the data boundary
   justifies it.
5. **Migration under load:** rename `products.name` to `title` with zero downtime — expand/contract in
   four deploys. Say what each deploy does.

### Mock interview: five rounds

- **Round 1 (15 min, fundamentals):** Q1–Q10 from Part 2. Then: "explain `async def` vs `def` in
  FastAPI, with a gotcha."
- **Round 2 (20 min, data):** Q20–Q27. Then: "walk me through PATCH with a unique field."
- **Round 3 (25 min, transactions):** Q28–Q32. Then: "two transactions want the same two rows in
  opposite order — what happens?"
- **Round 4 (20 min, design):** "design an endpoint that transfers stock between two warehouses
  atomically." Listen for the row lock order and the movement audit trail.
- **Round 5 (20 min, ops):** Q36–Q39. Then: "the endpoint got slow after a traffic spike — walk me
  through your debugging process."

### Final check

You are ready when you can (a) explain every line in `app/services/order_service.py:55` from memory,
(b) run the race script and predict its output before running it, (c) answer any Part 2 question in
60 seconds, and (d) find three new pieces of dead code the guide did not list.