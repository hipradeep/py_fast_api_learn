from typing import Annotated

from fastapi import Depends, Query
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.services import InventoryService, OrderService, UserService

SessionDep = Annotated[Session, Depends(get_session)]


class Pagination:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="1 based page number")] = 1,
        page_size: Annotated[
            int | None, Query(ge=1, le=settings.MAX_PAGE_SIZE, description="Items per page")
        ] = None,
    ) -> None:
        self.page = page
        self.page_size = page_size or settings.DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


PaginationDep = Annotated[Pagination, Depends()]


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_inventory_service(session: SessionDep) -> InventoryService:
    return InventoryService(session)


def get_order_service(session: SessionDep) -> OrderService:
    return OrderService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
InventoryServiceDep = Annotated[InventoryService, Depends(get_inventory_service)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]