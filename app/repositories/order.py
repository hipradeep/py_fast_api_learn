from __future__ import annotations

from typing import Optional

from sqlmodel import Session, col, func, select

from app.models import Order, OrderStatus, User


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, order_id: int) -> Optional[Order]:
        return self.session.get(Order, order_id)

    def get_for_update(self, order_id: int) -> Optional[Order]:
        stmt = select(Order).where(col(Order.id) == order_id).with_for_update()
        return self.session.exec(stmt).first()

    def get_by_reference(self, reference: str) -> Optional[Order]:
        stmt = select(Order).where(col(Order.reference) == reference)
        return self.session.exec(stmt).first()

    def next_reference(self) -> str:
        """Builds a human friendly order reference such as ORD-000042."""
        max_id = self.session.exec(select(func.coalesce(func.max(Order.id), 0))).one()
        return f"ORD-{int(max_id) + 1:06d}"

    def list(
        self,
        *,
        offset: int,
        limit: int,
        user_id: Optional[int] = None,
        status: Optional[OrderStatus] = None,
    ) -> list[Order]:
        stmt = select(Order)
        count_stmt = select(func.count()).select_from(Order)

        if user_id is not None:
            stmt = stmt.where(Order.user_id == user_id)
            count_stmt = count_stmt.where(Order.user_id == user_id)

        if status is not None:
            stmt = stmt.where(Order.status == status)
            count_stmt = count_stmt.where(Order.status == status)

        stmt = stmt.order_by(col(Order.id).desc()).offset(offset).limit(limit)
        return list(self.session.exec(stmt).all())

    def count(
        self,
        *,
        user_id: Optional[int] = None,
        status: Optional[OrderStatus] = None,
    ) -> int:
        stmt = select(func.count()).select_from(Order)

        if user_id is not None:
            stmt = stmt.where(Order.user_id == user_id)

        if status is not None:
            stmt = stmt.where(Order.status == status)

        return int(self.session.exec(stmt).one())

    def add(self, order: Order) -> Order:
        self.session.add(order)
        self.session.flush()
        self.session.refresh(order)
        return order

    def save(self, order: Order) -> Order:
        self.session.add(order)
        self.session.flush()
        self.session.refresh(order)
        return order

    def user_exists(self, user_id: int) -> bool:
        stmt = select(func.count()).select_from(User).where(User.id == user_id)
        return int(self.session.exec(stmt).one()) > 0