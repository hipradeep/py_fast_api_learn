from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlmodel import Session

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models import (
    ALLOWED_STATUS_TRANSITIONS,
    TERMINAL_STATUSES,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    StockMovement,
    StockMovementType,
    utc_now,
)
from app.repositories.order import OrderRepository
from app.repositories.product import ProductRepository
from app.repositories.user import UserRepository
from app.schemas.order import OrderCreate, OrderStatusUpdate

CENTS = Decimal("0.01")


def money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.products = ProductRepository(session)
        self.users = UserRepository(session)

    def get_order(self, order_id: int) -> Order:
        order = self.orders.get(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        return order

    def list_orders(
        self,
        *,
        offset: int,
        limit: int,
        user_id: Optional[int] = None,
        status: Optional[OrderStatus] = None,
    ) -> tuple[list[Order], int]:
        items = self.orders.list(offset=offset, limit=limit, user_id=user_id, status=status)
        total = self.orders.count(user_id=user_id, status=status)
        return items, total

    def create_order(self, payload: OrderCreate) -> Order:
        user = self.users.get(payload.user_id)
        if user is None:
            raise NotFoundError(f"User {payload.user_id} not found")
        if not user.is_active:
            raise BusinessRuleError(f"User {user.email} is inactive and cannot place orders")

        requested = [item.product_id for item in payload.items]
        locked_products = self.products.get_many_for_update(requested)

        found_ids = {p.id for p in locked_products}
        missing = [pid for pid in requested if pid not in found_ids]
        if missing:
            raise NotFoundError(f"Product(s) not found: {missing}")

        # Validate every line before mutating anything so a bad order changes no stock.
        for line in payload.items:
            product = self._index(locked_products, line.product_id)
            if not product.is_active:
                raise BusinessRuleError(f"Product {product.sku} is archived")
            if product.quantity_in_stock < line.quantity:
                raise BusinessRuleError(
                    f"Insufficient stock for {product.sku} ({product.name}): "
                    f"requested {line.quantity}, available {product.quantity_in_stock}",
                    details={
                        "product_id": product.id,
                        "sku": product.sku,
                        "requested": line.quantity,
                        "available": product.quantity_in_stock,
                    },
                )

        order = Order(
            reference=self.orders.next_reference(),
            user_id=user.id,
            status=OrderStatus.PENDING,
            shipping_address=payload.shipping_address,
            notes=payload.notes,
        )
        order = self.orders.add(order)

        subtotal = Decimal("0.00")
        for line in payload.items:
            product = self._index(locked_products, line.product_id)
            unit_price = money(product.unit_price)
            line_total = money(unit_price * line.quantity)
            subtotal += line_total

            self.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=line.quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                    product_name_snapshot=product.name,
                )
            )

            product.quantity_in_stock -= line.quantity
            self.products.add_movement(
                self._build_sale_movement(
                    product=product,
                    quantity=line.quantity,
                    order_id=order.id,
                )
            )

        order.subtotal = money(subtotal)
        order.tax_amount = money(subtotal * payload.tax_rate)
        order.total_amount = money(order.subtotal + order.tax_amount)

        return self.orders.save(order)

    def update_status(self, order_id: int, payload: OrderStatusUpdate) -> Order:
        order = self.orders.get_for_update(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")

        current = OrderStatus(order.status)
        target = OrderStatus(payload.status)

        if target == current:
            raise ConflictError(f"Order is already in status '{current.value}'")

        if current in TERMINAL_STATUSES:
            raise BusinessRuleError(
                f"Order {order.reference} is already {current.value} and cannot change status"
            )

        allowed = ALLOWED_STATUS_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise BusinessRuleError(
                f"Cannot move order from '{current.value}' to '{target.value}'. "
                f"Allowed: {sorted(s.value for s in allowed) or 'none'}",
                details={
                    "current_status": current.value,
                    "requested_status": target.value,
                    "allowed": sorted(s.value for s in allowed),
                },
            )

        if target == OrderStatus.CANCELLED:
            self._restock_cancelled_order(order)

        order.status = target
        if payload.notes:
            order.notes = payload.notes
        if target == OrderStatus.CANCELLED:
            order.cancelled_at = utc_now()

        return self.orders.save(order)

    def cancel_order(self, order_id: int, reason: Optional[str] = None) -> Order:
        return self.update_status(
            order_id,
            OrderStatusUpdate(status=OrderStatus.CANCELLED, notes=reason),
        )

    def _restock_cancelled_order(self, order: Order) -> None:
        if not order.items:
            return

        locked = {
            p.id: p
            for p in self.products.get_many_for_update([item.product_id for item in order.items])
        }
        for item in order.items:
            product = locked.get(item.product_id)
            if product is None:
                raise NotFoundError(f"Product {item.product_id} no longer exists")
            product.quantity_in_stock += item.quantity
            self.products.add_movement(
                self._build_restock_movement(
                    product=product,
                    quantity=item.quantity,
                    order_id=order.id,
                )
            )

    def _build_sale_movement(
        self, *, product: Product, quantity: int, order_id: int
    ) -> StockMovement:
        return StockMovement(
            product_id=product.id,
            order_id=order_id,
            movement_type=StockMovementType.SALE,
            quantity_change=-quantity,
            quantity_after=product.quantity_in_stock,
            reason=f"Stock issued for order {order_id}",
        )

    def _build_restock_movement(
        self, *, product: Product, quantity: int, order_id: int
    ) -> StockMovement:
        return StockMovement(
            product_id=product.id,
            order_id=order_id,
            movement_type=StockMovementType.ORDER_CANCELLATION,
            quantity_change=quantity,
            quantity_after=product.quantity_in_stock,
            reason=f"Stock returned by cancelled order {order_id}",
        )

    @staticmethod
    def _index(products: list[Product], product_id: int) -> Product:
        for product in products:
            if product.id == product_id:
                return product
        raise NotFoundError(f"Product {product_id} not found")