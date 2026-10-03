from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, computed_field

from app.models.enums import StockMovementType
from app.schemas.common import ORMModel


class ProductBase(ORMModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    unit_price: Decimal = Field(default=Decimal("0.00"), gt=0, max_digits=12, decimal_places=2)
    quantity_in_stock: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=10, ge=0)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ORMModel):
    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    unit_price: Optional[Decimal] = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    reorder_level: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class StockAdjustment(ORMModel):
    quantity_delta: int = Field(
        description="Signed change in stock. Negative values write stock off."
    )
    reason: Optional[str] = Field(default=None, max_length=255)


class ProductRead(ProductBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def is_low_stock(self) -> bool:
        return self.quantity_in_stock <= self.reorder_level


class StockMovementRead(ORMModel):
    id: int
    product_id: int
    order_id: Optional[int]
    movement_type: StockMovementType
    quantity_change: int
    quantity_after: int
    reason: Optional[str]
    created_at: datetime