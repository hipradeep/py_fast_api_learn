from decimal import Decimal
from typing import Optional

from sqlmodel import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models import Product, StockMovement, StockMovementType
from app.repositories.product import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate


class InventoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProductRepository(session)

    def get_product(self, product_id: int) -> Product:
        product = self.repo.get(product_id)
        if product is None:
            raise NotFoundError(f"Product {product_id} not found")
        return product

    def list_products(
        self,
        *,
        offset: int,
        limit: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        low_stock_only: bool = False,
    ) -> tuple[list[Product], int]:
        items = self.repo.list(
            offset=offset,
            limit=limit,
            search=search,
            is_active=is_active,
            low_stock_only=low_stock_only,
        )
        total = self.repo.count(
            search=search, is_active=is_active, low_stock_only=low_stock_only
        )
        return items, total

    def create_product(self, payload: ProductCreate) -> Product:
        sku = payload.sku.strip().upper()
        if self.repo.get_by_sku(sku) is not None:
            raise ConflictError(f"SKU {sku} already exists")

        product = Product(
            sku=sku,
            name=payload.name,
            description=payload.description,
            unit_price=payload.unit_price,
            quantity_in_stock=0,
            reorder_level=payload.reorder_level,
        )
        product = self.repo.add(product)

        if payload.quantity_in_stock > 0:
            self._apply_stock_change(
                product=product,
                delta=payload.quantity_in_stock,
                movement_type=StockMovementType.INITIAL_STOCK,
                reason="Initial stock on product creation",
            )
            product = self.repo.save(product)
        return product

    def update_product(self, product_id: int, payload: ProductUpdate) -> Product:
        product = self.get_product(product_id)
        data = payload.model_dump(exclude_unset=True)

        if "sku" in data and data["sku"]:
            new_sku = data["sku"].strip().upper()
            if new_sku != product.sku and self.repo.get_by_sku(new_sku) is not None:
                raise ConflictError(f"SKU {new_sku} already exists")
            data["sku"] = new_sku

        for field, value in data.items():
            setattr(product, field, value)

        return self.repo.save(product)

    def adjust_stock(
        self,
        product_id: int,
        quantity_delta: int,
        reason: Optional[str] = None,
        movement_type: StockMovementType = StockMovementType.MANUAL_ADJUSTMENT,
    ) -> Product:
        """Single entry point for changing stock so the audit log is never bypassed."""
        if quantity_delta == 0:
            raise BusinessRuleError("quantity_delta must not be zero")

        products = self.repo.get_many_for_update([product_id])
        if not products:
            raise NotFoundError(f"Product {product_id} not found")

        product = products[0]
        if not product.is_active:
            raise BusinessRuleError(f"Product {product.sku} is archived and cannot be stocked")

        self._apply_stock_change(
            product=product,
            delta=quantity_delta,
            movement_type=movement_type,
            reason=reason,
        )
        return self.repo.save(product)

    def restock(self, product_id: int, quantity: int, reason: Optional[str] = None) -> Product:
        if quantity <= 0:
            raise BusinessRuleError("Restock quantity must be greater than zero")
        return self.adjust_stock(
            product_id,
            quantity,
            reason=reason or "Restock",
            movement_type=StockMovementType.RESTOCK,
        )

    def list_low_stock(self) -> list[Product]:
        return self.repo.list_low_stock()

    def inventory_summary(self) -> dict:
        return {
            "total_products": self.repo.count(),
            "active_products": self.repo.count(is_active=True),
            "low_stock_count": self.repo.count(low_stock_only=True),
            "out_of_stock_count": self.repo.count_out_of_stock(),
            "total_inventory_value": self.repo.total_inventory_value(),
        }

    def list_movements(
        self,
        *,
        product_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[StockMovement], int]:
        if product_id is not None:
            self.get_product(product_id)
        items = self.repo.list_movements(product_id=product_id, offset=offset, limit=limit)
        return items, self.repo.count_movements(product_id=product_id)

    def _apply_stock_change(
        self,
        *,
        product: Product,
        delta: int,
        movement_type: StockMovementType,
        reason: Optional[str],
        order_id: Optional[int] = None,
    ) -> None:
        new_quantity = product.quantity_in_stock + delta
        if new_quantity < 0:
            raise BusinessRuleError(
                f"Cannot remove {abs(delta)} units of {product.sku}: "
                f"only {product.quantity_in_stock} in stock"
            )

        product.quantity_in_stock = new_quantity
        self.repo.add_movement(
            StockMovement(
                product_id=product.id,
                order_id=order_id,
                movement_type=movement_type,
                quantity_change=delta,
                quantity_after=new_quantity,
                reason=reason,
            )
        )

    def _decrement_stock_for_order(
        self,
        *,
        product: Product,
        quantity: int,
        order_id: Optional[int],
    ) -> None:
        self._apply_stock_change(
            product=product,
            delta=-quantity,
            movement_type=StockMovementType.SALE,
            reason=f"Stock issued for order {order_id}",
            order_id=order_id,
        )

    def _restore_stock_for_order(
        self,
        *,
        product: Product,
        quantity: int,
        order_id: Optional[int],
    ) -> None:
        self._apply_stock_change(
            product=product,
            delta=quantity,
            movement_type=StockMovementType.ORDER_CANCELLATION,
            reason=f"Stock returned by cancelled order {order_id}",
            order_id=order_id,
        )

    def to_decimal(self, value: Decimal | int | float) -> Decimal:
        return Decimal(str(value))