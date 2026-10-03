from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Enum
from sqlmodel import Field, Relationship

from app.models.base import TimestampMixin
from app.models.enums import StockMovementType

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.product import Product

stock_movement_type = Enum(
    StockMovementType,
    name="stockmovementtype",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class StockMovement(TimestampMixin, table=True):
    """Immutable audit log of every quantity change on a product."""

    __tablename__ = "stock_movements"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.id", index=True, nullable=False)
    order_id: Optional[int] = Field(
        default=None, foreign_key="orders.id", index=True, nullable=True
    )
    movement_type: StockMovementType = Field(
        sa_column=Column(stock_movement_type, nullable=False, index=True)
    )
    quantity_change: int = Field(nullable=False)
    quantity_after: int = Field(nullable=False)
    reason: Optional[str] = Field(default=None, max_length=255)

    product: "Product" = Relationship(back_populates="stock_movements")

    def __repr__(self) -> str:
        return (
            f"StockMovement(product_id={self.product_id!r}, "
            f"type={self.movement_type!r}, change={self.quantity_change!r})"
        )