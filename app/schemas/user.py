from datetime import datetime
from typing import Optional

from pydantic import EmailStr, Field

from app.schemas.common import ORMModel


class UserBase(ORMModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=32)


class UserCreate(UserBase):
    pass


class UserUpdate(ORMModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=32)
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime