# Alembic

Schema versioning for this project. Alembic turns the difference between your SQLModel
classes and the live database into ordered, reviewable, reversible Python files — so
`users`, `products`, `orders`, `order_items` and `stock_movements` are deployed with
`git`, and every environment can be rebuilt from empty to `head` with one command.

## The problem it solves

Three common ways to change a database, and what goes wrong with each:

| Approach | Failure |
|---|---|
| Hand-run `ALTER TABLE` in psql | Nothing records it. The next developer or CI has no way to reproduce the schema. |
| `SQLModel.metadata.create_all()` (`app/core/database.py:26`) | Creates only *missing* tables. It never alters, drops or renames one. Schema silently drifts from the models. |
| `drop_all()` then `create_all()` | Destroys production data. |

Alembic is the versioned middle path. Each change is a file in `alembic/versions/`, and
Alembic tracks which files have been applied in a table called `alembic_version`.

## How this project is wired

| File | Job |
|---|---|
| `alembic.ini` | Points at the migration folder and logging config. Deliberately has **no** `sqlalchemy.url`. |
| `alembic/env.py` | Builds the connection, wires `target_metadata`, runs migrations. |
| `alembic/script.py.mako` | Template for every new migration file. |
| `alembic/versions/` | The migration history, one file per change. |
| `alembic/versions/f5e85f10ac53_initial_schema.py` | The current single revision: full initial schema. |

Four lines in `alembic/env.py` carry all the weight:

```python
import app.models                                   # env.py:7  registers every model
config.set_main_option("sqlalchemy.url", settings.database_url)  # env.py:11
target_metadata = SQLModel.metadata                 # env.py:16  what we diff against
```

- **`import app.models`** — SQLModel only puts a table on `SQLModel.metadata` once its
  class is imported. `app/models/__init__.py` imports every model, so one import here
  makes `User`, `Product`, `Order`, `OrderItem` and `StockMovement` visible to
  autogenerate. Add a new model file and you must add it to `app/models/__init__.py`,
  or autogenerate will silently ignore it.
- **The DB URL comes from `settings`**, so migrations read the same `.env` as the app.
  Because the URL lives in code, `alembic.ini` needs no password and no
  `sqlalchemy.url` key at all. Two configs, one source of truth.
- **`target_metadata`** is the "desired" schema. Autogenerate compares it against a live
  connection to produce the operations.

`compare_type=True` is passed in both modes (`env.py:26`, `env.py:41`). Without it,
autogenerate ignores column type changes and will never notice
`Numeric(12, 2)` becoming `Numeric(14, 2)`.

`NullPool` is used for the migration connection (`env.py:35`) — migrations are a
one-shot process, so there is nothing to gain from pooling.

## Vocabulary

| Term | Meaning |
|---|---|
| **revision** | One migration file. Identified by a short random id, e.g. `f5e85f10ac53`. |
| **`down_revision`** | The revision this file follows. `None` means it is the first. |
| **base** | The bottom of the chain, i.e. a revision with no parent. |
| **head** | The newest revision — the tip. Currently `f5e85f10ac53`. |
| **`upgrade()`** | Applies the change (forward). |
| **`downgrade()`** | Reverts it (backward). |
| **branch** | Two heads, meaning two independent lines of history that need `merge`. |
| **`stamp`** | Record a revision as applied *without* running it. |

The whole graph lives in those two variables, which is why the id in the filename and
the `revision` string inside must match:

```python
revision = 'f5e85f10ac53'        # id of THIS file
down_revision = None             # id of the file it follows
```

## Everyday commands

```bash
alembic current                  # what revision does this database have?
alembic heads                    # what revision is the newest file?
alembic history                  # full chain, oldest first
alembic history --verbose        # ...with full messages and paths
alembic show f5e85f10ac53        # print one revision's detail
alembic check                    # exit 1 if the models and DB have diverged (CI)

alembic revision --autogenerate -m "add brand to products"   # detect + write file
alembic upgrade head             # apply everything up to the newest revision
alembic downgrade -1             # undo the one most recent migration
alembic downgrade f5e85f10ac53   # undo back to (and including) that revision
alembic downgrade base           # drop everything this history created

alembic upgrade head --sql       # print the SQL instead of running it
alembic branches                 # list branch points
alembic merge -m "merge heads" <rev1> <rev2>
alembic stamp head               # mark DB as current without running anything
```

Run them from the project root so `alembic.ini` and `.env` are found. Use
`.\.venv\Scripts\alembic.exe` if the venv is not on `PATH`.

`--sql` (offline mode) is the safest way to read a migration. Offline mode is wired at
`env.py:19-28`: it substitutes literal values for bind parameters instead of connecting
to a database. Note that offline SQL can be subtly wrong for anything requiring
introspection, so treat it as a review aid, not a deploy mechanism.

## Adding a column, end to end

1. Change the model.

```python
# app/models/product.py
brand: Optional[str] = Field(default=None, max_length=64, index=True)
```

2. Generate the migration.

```bash
alembic revision --autogenerate -m "add brand to products"
```

Alembic opens a connection, reflects the live `products` table, diffs it against
`SQLModel.metadata`, and writes something like:

```python
def upgrade() -> None:
    op.add_column('products', sa.Column('brand', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_products_brand'), 'products', ['brand'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_products_brand'), table_name='products')
    op.drop_column('products', 'brand')
```

3. **Read the generated file.** Autogenerate is a first draft, not an answer. Drop the
   `# ### commands auto generated by Alembic - please adjust! ###` markers once you have
   reviewed the body.

4. Apply it.

```bash
alembic upgrade head
```

5. Commit the model change and the migration **in the same commit**. A model change
   without its migration will pass CI and break the next deploy.

6. Confirm nothing is left over: `alembic check` should now exit 0, and a fresh
   `alembic revision --autogenerate` should produce an empty file.

## What autogenerate cannot see

This is the single most important thing to know. Autogenerate diffs *model metadata*
against *database schema* — it has no idea what your data means.

| Change | Autogenerate behaviour |
|---|---|
| **Rename a column** | Emits `drop_column` + `add_column`. **Data is lost.** Must be hand-written. |
| **Rename a table** | Same problem — drop + create. |
| **Add a value to a Python enum** | Emits **nothing**. The Postgres type already exists. |
| **Rename an enum value** | Nothing. |
| **Make a column nullable / non-nullable** | Often wrong, because it ignores existing rows. |
| **Add a column with a Python-side `default`** | Misses the `server_default`, so old rows get nothing. |
| **Change a `CheckConstraint` / partial index** | Frequently missed. |
| **Any data backfill** | Impossible. Requires `op.execute`. |

So autogenerate is a *starting point that must be reviewed*, which is why the template
ships with the "please adjust" markers.

## Hand-editing migrations

### Add a value to an enum

Adding `RETURNED = "returned"` to `OrderStatus` (`app/models/enums.py`) produces no
migration. Write it yourself:

```python
def upgrade() -> None:
    op.execute("ALTER TYPE orderstatus ADD VALUE 'returned'")

def downgrade() -> None:
    op.execute("UPDATE orders SET status = 'cancelled' WHERE status = 'returned'")
    # Postgres cannot remove a value from an enum. Recreate the type:
    op.execute("ALTER TABLE orders ALTER COLUMN status DROP DEFAULT")
    op.execute("DROP TYPE orderstatus")
    op.execute("CREATE TYPE orderstatus AS ENUM "
               "('pending','confirmed','shipped','delivered','cancelled')")
    op.execute("ALTER TABLE orders ALTER COLUMN status TYPE orderstatus "
               "USING status::text::orderstatus")
```

The `USING` clause is required: Postgres will not implicitly cast `text` back to the new
enum type.

Two caveats. Removing an enum value is inherently lossy — the `downgrade` above has to
decide where the rows that used `returned` go, and there is no safe answer. And
`ALTER TYPE ... ADD VALUE` cannot be used in the same transaction that first uses the
new value, so on PostgreSQL 12+ put it in its own migration.

### Rename a column without losing data

```python
def upgrade() -> None:
    op.alter_column('products', 'name', new_column_name='product_name')

def downgrade() -> None:
    op.alter_column('products', 'product_name', new_column_name='name')
```

### Add a NOT NULL column safely

`op.add_column(..., nullable=False)` with no default fails on a non-empty table, and
adding a default in one step rewrites every row (and holds a lock while it does). Use
three migrations, or three clearly separated steps in one:

```python
def upgrade() -> None:
    # 1. nullable, no default — instant, no rewrite
    op.add_column('products', sa.Column('brand', sa.String(length=64), nullable=True))
    # 2. backfill in batches so you do not hold one huge transaction
    op.execute("UPDATE products SET brand = 'generic' WHERE brand IS NULL")
    # 3. enforce the constraint
    op.alter_column('products', 'brand', nullable=False)
```

### Alter a column type

```python
def upgrade() -> None:
    op.alter_column('orders', 'subtotal',
                    type_=sa.Numeric(precision=16, scale=2),
                    existing_type=sa.Numeric(precision=14, scale=2))
```

`existing_type` is required — without it Alembic cannot render the `USING` clause.
Always confirm with `alembic upgrade head --sql`.

### Use `batch_alter_table` for anything SQLite

SQLite has almost no `ALTER TABLE`, so an alter is emulated by creating a temp table,
copying rows, swapping. `batch_alter_table` does that for you:

```python
with op.batch_alter_table('products') as batch_op:
    batch_op.alter_column('description', type_=sa.String(length=2000))
```

This project targets PostgreSQL only, but the pattern costs nothing and keeps the
migration portable to the SQLite scratch DB some people use locally.

### Data migrations

Schema migrations change structure; data migrations move rows. Keep both in one file
when they must succeed or fail together, and always make the data step idempotent
(`WHERE ... IS NULL`) so a re-run after a partial failure is harmless.

```python
def upgrade() -> None:
    connection = op.get_bind()
    products = sa.table('products',
                        sa.column('id', sa.Integer),
                        sa.column('name', sa.String))
    for row in connection.execute(products.select()):
        connection.execute(
            products.update()
            .where(products.c.id == row.id)
            .values(name=row.name.strip())
        )
```

`op.get_bind()` hands you the migration's own connection, which means your SQL runs in
the same transaction as the schema change and is rolled back with it.

### Drop an enum type

The existing initial migration shows the one thing autogenerate will not do for you —
Postgres keeps a named type after its last column disappears (`f5e85f10ac53_initial_schema.py:133`):

```python
def downgrade() -> None:
    op.execute('DROP TYPE IF EXISTS orderstatus')
    op.execute('DROP TYPE IF EXISTS stockmovementtype')
```

## Downgrade discipline

`downgrade()` is not optional. An unrevertible migration is a migration you cannot roll
back during an incident, and rollback is the first thing you reach for when a deploy
goes wrong.

Order your drops in reverse: indexes, then tables, then types. The existing
`downgrade()` is the reference — read `f5e85f10ac53_initial_schema.py:108-135`.

Dropping a column is destructive and there is no way to undo it. That is acceptable;
just be deliberate, and say so in the migration docstring.

## Deploying

```
1. git pull                      # migrations arrive with the code
2. alembic upgrade head          # before the new version serves traffic
3. uvicorn app.main:app
```

Two rules that matter:

- **Migrations are forward-only in production.** Rolling the app back past a migration
  is only safe if its `downgrade()` is genuinely correct. Expand/contract — add the new
  column, deploy code that writes both, backfill, then remove the old one — avoids the
  question entirely.
- **Never run `create_db_and_tables()` in production.** It is a local convenience
  (`app/core/database.py:26`) that creates missing tables without recording anything in
  `alembic_version`, leaving Alembic's idea of the schema permanently wrong.

Back up first. On a large table, `op.create_index()` should be
`CREATE INDEX CONCURRENTLY`, which Alembic supports via
`op.create_index(..., postgresql_concurrently=True)` and which therefore cannot run
inside the migration transaction — use `AUTOCOMMIT`.

## Verify it works

```bash
alembic downgrade base && alembic upgrade head     # full teardown and rebuild
```

Run that against a throwaway database. If it fails, your `downgrade()` is wrong or
incomplete, and you want to find that out now rather than during an incident.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Can't locate revision identified by '<id>'` | The database points at a revision no file provides. Usually an old `alembic_version` row after a history rewrite. Fix: `alembic stamp head` (only if the schema really does match) or `alembic stamp <correct-id>`. |
| Autogenerate produces an empty file, but the schema is wrong | A model is not imported by `app/models/__init__.py`, so it never reached `SQLModel.metadata`. |
| `Target database is not up to date` | Unapplied migrations are between the current revision and the target. Run `alembic upgrade head`. |
| Two heads after a rebase / parallel branch | Merge them: `alembic merge -m "merge heads" <rev1> <rev2>`. |
| Autogenerate tries to recreate existing tables | The DB was created by `create_all()` or an older tool and lacks Alembic's bookkeeping. Reconcile with `alembic stamp head`, or drop and rebuild with `alembic upgrade head`. |
| Changes made straight in psql are ignored | Autogenerate diffs models vs schema, but only for what it can *see*. Anything out-of-band must be mirrored in a migration or reverted. |
| `alembic.ini` missing `sqlalchemy.url` is expected here | The URL is injected from `settings` at `env.py:11`. Not a bug. |
| Model edits are not detected | The changed class is not reachable from `app/models/__init__.py`, so it never lands on `SQLModel.metadata`. Confirm the table is imported before rerunning autogenerate. |
| Autogenerate errors on import | An `app/models/*.py` file has a syntax or import error. `env.py:7` imports the package eagerly, so the CLI fails before any SQL runs. Fix the import. |

## A `.gitignore` note

`alembic/versions/` is committed. Some teams ignore it and generate migrations at deploy
time — never do that here. Migrations are code: they must be reviewed, versioned, and
rolled back with the release that needs them.

## Interview notes

Questions this setup is designed to answer:

- **"Why is the DB URL in `env.py` and not `alembic.ini`?"** One source of truth. The
  app and the migrations read the identical `Settings` object, so they cannot drift, and
  no credential is ever committed.
- **"Why `compare_type=True`?"** Because autogenerate ignores type changes without it —
  a silent-drift trap for a schema with `Decimal` money columns.
- **"How do you add a column to a 50M-row table?"** `add_column` nullable with no
  default, batched backfill, then set `NOT NULL`. Adding a default in one statement
  rewrites the table and blocks writes for the duration.
- **"How do you rename a column with no downtime?"** Rename via `ALTER ... RENAME`
  while old code still reads the old name — no, that breaks it. The real answer:
  expand/contract, or `add new column → dual-write → backfill → cut over → drop old`.
- **"What's `stamp` for?"** Telling Alembic the truth about a database it did not
  create, or moving the pointer without executing DDL.
- **"Why must `downgrade()` work?"** Rollback is your incident response. An irreversible
  migration means a bad deploy stays out.

## Cheatsheet

```bash
alembic revision --autogenerate -m "message"   # generate
alembic upgrade head                           # apply
alembic downgrade -1                           # undo one
alembic current                                # where am I?
alembic heads                                  # where is the tip?
alembic history                                # the chain
alembic check                                  # any drift? (CI)
alembic upgrade head --sql                     # review the SQL
```

Inside a migration:

```
op.add_column      op.drop_column       op.alter_column
op.create_table    op.drop_table        op.rename_table
op.create_index    op.drop_index
op.get_bind()                            # the connection, for data migrations
op.execute("...")                        # raw SQL
batch_alter_table()                      # table rebuild, for SQLite
```