from __future__ import annotations

from typing import Optional

from sqlmodel import Session, col, func, or_, select

from app.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: int) -> Optional[User]:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(col(User.email) == email.lower())
        return self.session.exec(stmt).first()

    def list(
        self,
        *,
        offset: int,
        limit: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> list[User]:
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)

        if search:
            pattern = f"%{search.lower()}%"
            condition = or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)

        stmt = stmt.order_by(User.id).offset(offset).limit(limit)
        return list(self.session.exec(stmt).all())

    def count(
        self,
        *,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        stmt = select(func.count()).select_from(User)

        if search:
            pattern = f"%{search.lower()}%"
            condition = or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
            stmt = stmt.where(condition)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        return int(self.session.exec(stmt).one())

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.session.delete(user)
        self.session.flush()