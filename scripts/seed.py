"""Seeds the database with demo users, products and orders.

Usage:
    python -m scripts.seed          # skip if data already exists
    python -m scripts.seed --force  # wipe existing rows first
"""

import argparse
from decimal import Decimal

from sqlmodel import Session, delete, select

from app.core.database import engine
from app.models import Order, OrderItem, Product, StockMovement, User
from app.services import InventoryService, OrderService, UserService
from app.models.enums import OrderStatus
from app.schemas.order import OrderCreate, OrderItemCreate, OrderStatusUpdate
from app.schemas.product import ProductCreate
from app.schemas.user import UserCreate

USERS = [
    {"email": "alice@example.com", "full_name": "Alice Johnson", "phone": "+15550100"},
    {"email": "bob@example.com", "full_name": "Bob Smith", "phone": "+15550101"},
    {"email": "carol@example.com", "full_name": "Carol Danvers", "phone": "+15550102"},
]

PRODUCTS = [
    {
        "sku": "LAPTOP-001",
        "name": "Pro Laptop 14",
        "description": "14 inch developer laptop, 32GB RAM",
        "unit_price": Decimal("1299.00"),
        "quantity_in_stock": 25,
        "reorder_level": 5,
    },
    {
        "sku": "MOUSE-002",
        "name": "Wireless Mouse",
        "description": "Ergonomic wireless mouse",
        "unit_price": Decimal("29.99"),
        "quantity_in_stock": 140,
        "reorder_level": 20,
    },
    {
        "sku": "MONITOR-003",
        "name": "27in 4K Monitor",
        "description": "IPS panel, USB-C docking",
        "unit_price": Decimal("449.50"),
        "quantity_in_stock": 12,
        "reorder_level": 5,
    },
    {
        "sku": "KEYBOARD-004",
        "name": "Mechanical Keyboard",
        "description": "Hot-swappable, brown switches",
        "unit_price": Decimal("89.00"),
        "quantity_in_stock": 4,
        "reorder_level": 10,
    },
    {
        "sku": "HEADSET-005",
        "name": "Noise Cancelling Headset",
        "description": "Over-ear, 30h battery",
        "unit_price": Decimal("199.99"),
        "quantity_in_stock": 0,
        "reorder_level": 8,
    },
]


def wipe(session: Session) -> None:
    for model in (StockMovement, OrderItem, Order, Product, User):
        session.exec(delete(model))
    session.commit()
    print("Cleared existing rows")


def seed(force: bool = False) -> None:
    with Session(engine) as session:
        already = session.exec(select(User.id).limit(1)).first()
        if already is not None and not force:
            print("Data already present. Re-run with --force to reseed.")
            return

        if force:
            wipe(session)

        users = UserService(session)
        inventory = InventoryService(session)
        orders = OrderService(session)

        created_users = []
        for payload in USERS:
            created_users.append(users.create_user(UserCreate(**payload)))
        print(f"Created {len(created_users)} users")

        created_products = []
        for payload in PRODUCTS:
            created_products.append(inventory.create_product(ProductCreate(**payload)))
        print(f"Created {len(created_products)} products")

        by_sku = {p.sku: p for p in created_products}

        # An order that pushes the keyboard below its reorder level.
        order_one = orders.create_order(
            OrderCreate(
                user_id=created_users[0].id,
                items=[
                    OrderItemCreate(product_id=by_sku["LAPTOP-001"].id, quantity=2),
                    OrderItemCreate(product_id=by_sku["MOUSE-002"].id, quantity=3),
                    OrderItemCreate(product_id=by_sku["KEYBOARD-004"].id, quantity=3),
                ],
                tax_rate=Decimal("0.08"),
                shipping_address="221B Baker Street, London",
                notes="Deliver during business hours",
            )
        )
        print(f"Created order {order_one.reference} total={order_one.total_amount}")

        # Second order, then cancelled to show stock returning to inventory.
        order_two = orders.create_order(
            OrderCreate(
                user_id=created_users[1].id,
                items=[
                    OrderItemCreate(product_id=by_sku["MONITOR-003"].id, quantity=1),
                ],
                tax_rate=Decimal("0.08"),
            )
        )
        orders.cancel_order(order_two.id, reason="Customer requested cancellation")
        print(f"Created and cancelled order {order_two.reference}")

        third = orders.create_order(
            OrderCreate(
                user_id=created_users[2].id,
                items=[
                    OrderItemCreate(product_id=by_sku["MOUSE-002"].id, quantity=5),
                ],
                tax_rate=Decimal("0.08"),
            )
        )
        orders.update_status(third.id, OrderStatusUpdate(status=OrderStatus.CONFIRMED))
        print(f"Created and confirmed order {third.reference}")

        low_stock = inventory.list_low_stock()
        session.commit()
        print(f"\nLow stock items: {', '.join(p.sku for p in low_stock) or 'none'}")
        print("Seed complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--force", action="store_true", help="delete existing rows first")
    args = parser.parse_args()
    seed(force=args.force)