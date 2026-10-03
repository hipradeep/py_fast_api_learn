from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlmodel import Session, col, func, or_, select

from app.models import Product, StockMovement


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, product_id: int) -> Optional[Product]:
        return self.session.get(Product, product_id)

    def get_by_sku(self, sku: str) -> Optional[Product]:
        stmt = select(Product).where(col(Product.sku) == sku)
        return self.session.exec(stmt).first()

    def get_many_for_update(self, product_ids: list[int]) -> list[Product]:
        """Loads products with SELECT ... FOR UPDATE so concurrent orders cannot
        oversell the same row."""
        if not product_ids:
            return []
        stmt = (
            select(Product)
            .where(col(Product.id).in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
        )
        return list(self.session.exec(stmt).all())

    def list(
        self,
        *,
        offset: int,
        limit: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        low_stock_only: bool = False,
    ) -> list[Product]:
        stmt = select(Product)
        count_stmt = select(func.count()).select_from(Product)

        if search:
            pattern = f"%{search.lower()}%"
            condition = or_(
                func.lower(Product.name).like(pattern),
                func.lower(Product.sku).like(pattern),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
            count_stmt = count_stmt.where(Product.is_active == is_active)

        if low_stock_only:
            condition = Product.quantity_in_stock <= Product.reorder_level
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Product.id).offset(offset).limit(limit)
        return list(self.session.exec(stmt).all())

    def count(
        self,
        *,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        low_stock_only: bool = False,
    ) -> int:
        stmt = select(func.count()).select_from(Product)

        if search:
            pattern = f"%{search.lower()}%"
            condition = or_(
                func.lower(Product.name).like(pattern),
                func.lower(Product.sku).like(pattern),
            )
            stmt = stmt.where(condition)

        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)

        if low_stock_only:
            stmt = stmt.where(Product.quantity_in_stock <= Product.reorder_level)

        return int(self.session.exec(stmt).one())

    def list_low_stock(self) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.quantity_in_stock <= Product.reorder_level)
            .order_by(Product.quantity_in_stock)
        )
        return list(self.session.exec(stmt).all())

    def count_out_of_stock(self) -> int:
        stmt = select(func.count()).select_from(Product).where(Product.quantity_in_stock <= 0)
        return int(self.session.exec(stmt).one())

    def total_inventory_value(self) -> Decimal:
        stmt = select(
            func.coalesce(
                func.sum(Product.quantity_in_stock * Product.unit_price), 0
            )
        ).select_from(Product)
        return Decimal(str(self.session.exec(stmt).one()))

    def add(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        self.session.refresh(product)
        return product

    def save(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        self.session.refresh(product)
        return product

    def delete(self, product: Product) -> None:
        self.session.delete(product)
        self.session.flush()

    def add_movement(self, movement: StockMovement) -> StockMovement:
        self.session.add(movement)
        self.session.flush()
        return movement

    def list_movements(
        self,
        *,
        product_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[StockMovement]:
        stmt = select(StockMovement)
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
        stmt = stmt.order_by(col(StockMovement.id).desc()).offset(offset).limit(limit)
        return list(self.session.exec(stmt).all())

    def count_movements(self, *, product_id: Optional[int] = None) -> int:
        stmt = select(func.count()).select_from(StockMovement)
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
        return int(self.session.exec(stmt).one())