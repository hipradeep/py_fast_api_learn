from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class User(TimestampMixin, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, unique=True, index=True)
    full_name: str = Field(max_length=255)
    phone: Optional[str] = Field(default=None, max_length=32)
    is_active: bool = Field(default=True, index=True)

    orders: list["Order"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"