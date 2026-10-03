from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Enum
from sqlmodel import Field, Relationship, SQLModel

from app.models.base import TimestampMixin
from app.models.enums import OrderStatus

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User

# values_callable makes Postgres store the lowercase values ("pending") that the
# public API uses instead of the Python member names ("PENDING").
order_status_type = Enum(
    OrderStatus,
    name="orderstatus",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Order(TimestampMixin, table=True):
    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    reference: str = Field(max_length=32, unique=True, index=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    status: OrderStatus = Field(
        default=OrderStatus.PENDING,
        sa_column=Column(order_status_type, nullable=False, index=True),
    )
    subtotal: Decimal = Field(
        default=Decimal("0.00"), max_digits=14, decimal_places=2, nullable=False
    )
    tax_amount: Decimal = Field(
        default=Decimal("0.00"), max_digits=14, decimal_places=2, nullable=False
    )
    total_amount: Decimal = Field(
        default=Decimal("0.00"), max_digits=14, decimal_places=2, nullable=False
    )
    shipping_address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1000)
    cancelled_at: Optional[datetime] = None

    user: "User" = Relationship(back_populates="orders")
    items: list["OrderItem"] = Relationship(
        back_populates="order",
        cascade_delete=True,
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)

    def __repr__(self) -> str:
        return f"Order(id={self.id!r}, reference={self.reference!r}, status={self.status!r})"


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True, nullable=False)
    product_id: int = Field(foreign_key="products.id", index=True, nullable=False)
    quantity: int = Field(nullable=False)
    unit_price: Decimal = Field(
        default=Decimal("0.00"), max_digits=12, decimal_places=2, nullable=False
    )
    line_total: Decimal = Field(
        default=Decimal("0.00"), max_digits=14, decimal_places=2, nullable=False
    )
    # Snapshot of product name at purchase time so historic invoices stay correct
    # even if the product is later renamed.
    product_name_snapshot: str = Field(max_length=255)

    order: "Order" = Relationship(back_populates="items")
    product: "Product" = Relationship(back_populates="order_items")

    def __repr__(self) -> str:
        return f"OrderItem(order_id={self.order_id!r}, product_id={self.product_id!r}, qty={self.quantity!r})"