from typing import Annotated, Optional

from fastapi import APIRouter, Path, Query, status

from app.api.deps import OrderServiceDep, PaginationDep
from app.models.enums import OrderStatus
from app.schemas.common import Page
from app.schemas.order import OrderCreate, OrderRead, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=Page[OrderRead], summary="List orders")
def list_orders(
    service: OrderServiceDep,
    pagination: PaginationDep,
    user_id: Annotated[Optional[int], Query(ge=1)] = None,
    order_status: Annotated[Optional[OrderStatus], Query(alias="status")] = None,
) -> Page[OrderRead]:
    items, total = service.list_orders(
        offset=pagination.offset,
        limit=pagination.limit,
        user_id=user_id,
        status=order_status,
    )
    return Page.build(items, total, pagination.page, pagination.limit)


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order (reserves and decrements stock)",
)
def create_order(payload: OrderCreate, service: OrderServiceDep) -> OrderRead:
    return service.create_order(payload)


@router.get("/{order_id}", response_model=OrderRead, summary="Get one order")
def get_order(
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
) -> OrderRead:
    return service.get_order(order_id)


@router.patch(
    "/{order_id}/status",
    response_model=OrderRead,
    summary="Move an order to a new status (cancelling restores stock)",
)
def update_order_status(
    payload: OrderStatusUpdate,
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
) -> OrderRead:
    return service.update_status(order_id, payload)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderRead,
    summary="Cancel an order and return stock to inventory",
)
def cancel_order(
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    reason: Annotated[Optional[str], Query(max_length=1000)] = None,
) -> OrderRead:
    return service.cancel_order(order_id, reason)