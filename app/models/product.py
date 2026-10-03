from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import OrderItem
    from app.models.stock_movement import StockMovement


class Product(TimestampMixin, table=True):
    __tablename__ = "products"

    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(max_length=64, unique=True, index=True)
    name: str = Field(max_length=255, index=True)
    description: Optional[str] = Field(default=None, max_length=1000)
    unit_price: Decimal = Field(
        default=Decimal("0.00"), max_digits=12, decimal_places=2, nullable=False
    )
    quantity_in_stock: int = Field(default=0, nullable=False)
    reorder_level: int = Field(default=10, nullable=False)
    is_active: bool = Field(default=True, index=True)

    order_items: list["OrderItem"] = Relationship(back_populates="product")
    stock_movements: list["StockMovement"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_in_stock <= self.reorder_level

    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, sku={self.sku!r}, stock={self.quantity_in_stock!r})"