from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, model_validator

from app.models.enums import OrderStatus
from app.schemas.common import ORMModel


class OrderItemCreate(ORMModel):
    product_id: int
    quantity: int = Field(gt=0, le=10_000)


class OrderItemRead(ORMModel):
    id: int
    product_id: int
    product_name_snapshot: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderCreate(ORMModel):
    user_id: int
    items: list[OrderItemCreate] = Field(min_length=1)
    tax_rate: Decimal = Field(
        default=Decimal("0.00"), ge=0, le=1, max_digits=5, decimal_places=4
    )
    shipping_address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _no_duplicate_products(self) -> "OrderCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate product_id values are not allowed in one order")
        return self


class OrderStatusUpdate(ORMModel):
    status: OrderStatus
    notes: Optional[str] = Field(default=None, max_length=1000)


class OrderRead(ORMModel):
    id: int
    reference: str
    user_id: int
    status: OrderStatus
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    shipping_address: Optional[str]
    notes: Optional[str]
    cancelled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead]


class OrderSummaryRead(ORMModel):
    id: int
    reference: str
    user_id: int
    status: OrderStatus
    total_amount: Decimal
    created_at: datetime