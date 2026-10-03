from typing import Optional

from sqlmodel import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import TERMINAL_STATUSES, User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = UserRepository(session)

    def get_user(self, user_id: int) -> User:
        user = self.repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    def list_users(
        self,
        *,
        offset: int,
        limit: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[list[User], int]:
        items = self.repo.list(offset=offset, limit=limit, search=search, is_active=is_active)
        total = self.repo.count(search=search, is_active=is_active)
        return items, total

    def create_user(self, payload: UserCreate) -> User:
        email = payload.email.lower()
        if self.repo.get_by_email(email) is not None:
            raise ConflictError(f"Email {email} is already registered")

        user = User(
            email=email,
            full_name=payload.full_name,
            phone=payload.phone,
        )
        return self.repo.add(user)

    def update_user(self, user_id: int, payload: UserUpdate) -> User:
        user = self.get_user(user_id)
        data = payload.model_dump(exclude_unset=True)

        if "email" in data and data["email"]:
            new_email = data["email"].lower()
            if new_email != user.email and self.repo.get_by_email(new_email) is not None:
                raise ConflictError(f"Email {new_email} is already registered")
            data["email"] = new_email

        for field, value in data.items():
            setattr(user, field, value)

        return self.repo.save(user)

    def deactivate_user(self, user_id: int) -> User:
        user = self.get_user(user_id)
        user.is_active = False
        return self.repo.save(user)

    def delete_user(self, user_id: int) -> None:
        user = self.get_user(user_id)
        open_orders = [o for o in user.orders if o.status not in TERMINAL_STATUSES]
        if open_orders:
            raise ConflictError(
                "Cannot delete a user that still has open orders. "
                "Deactivate the user instead."
            )
        self.repo.delete(user)