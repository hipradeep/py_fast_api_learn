import enum


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


ALLOWED_STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

TERMINAL_STATUSES: set[OrderStatus] = {OrderStatus.DELIVERED, OrderStatus.CANCELLED}


class StockMovementType(str, enum.Enum):
    INITIAL_STOCK = "initial_stock"
    RESTOCK = "restock"
    SALE = "sale"
    ORDER_CANCELLATION = "order_cancellation"
    MANUAL_ADJUSTMENT = "manual_adjustment"
    DAMAGE_WRITE_OFF = "damage_write_off"