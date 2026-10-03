from typing import Annotated, Optional

from fastapi import APIRouter, Path, Query, status

from app.api.deps import InventoryServiceDep, PaginationDep
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductUpdate,
    StockAdjustment,
    StockMovementRead,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/products", response_model=Page[ProductRead], summary="List products")
def list_products(
    service: InventoryServiceDep,
    pagination: PaginationDep,
    search: Annotated[Optional[str], Query(description="Match name or SKU")] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
    low_stock: Annotated[bool, Query(description="Only items at or below reorder level")] = False,
) -> Page[ProductRead]:
    items, total = service.list_products(
        offset=pagination.offset,
        limit=pagination.limit,
        search=search,
        is_active=is_active,
        low_stock_only=low_stock,
    )
    return Page.build(items, total, pagination.page, pagination.limit)


@router.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
)
def create_product(payload: ProductCreate, service: InventoryServiceDep) -> ProductRead:
    return service.create_product(payload)


@router.get("/products/{product_id}", response_model=ProductRead, summary="Get one product")
def get_product(
    service: InventoryServiceDep,
    product_id: Annotated[int, Path(ge=1)],
) -> ProductRead:
    return service.get_product(product_id)


@router.patch(
    "/products/{product_id}", response_model=ProductRead, summary="Update product metadata"
)
def update_product(
    payload: ProductUpdate,
    service: InventoryServiceDep,
    product_id: Annotated[int, Path(ge=1)],
) -> ProductRead:
    return service.update_product(product_id, payload)


@router.post(
    "/products/{product_id}/stock",
    response_model=ProductRead,
    summary="Adjust stock by a signed quantity",
)
def adjust_stock(
    payload: StockAdjustment,
    service: InventoryServiceDep,
    product_id: Annotated[int, Path(ge=1)],
) -> ProductRead:
    return service.adjust_stock(product_id, payload.quantity_delta, payload.reason)


@router.post(
    "/products/{product_id}/restock",
    response_model=ProductRead,
    summary="Add stock (positive quantity only)",
)
def restock(
    service: InventoryServiceDep,
    product_id: Annotated[int, Path(ge=1)],
    quantity: Annotated[int, Query(gt=0)],
    reason: Annotated[Optional[str], Query(max_length=255)] = None,
) -> ProductRead:
    return service.restock(product_id, quantity, reason)


@router.get(
    "/products/{product_id}/movements",
    response_model=Page[StockMovementRead],
    summary="Stock movement history for a product",
)
def list_product_movements(
    service: InventoryServiceDep,
    pagination: PaginationDep,
    product_id: Annotated[int, Path(ge=1)],
) -> Page[StockMovementRead]:
    items, total = service.list_movements(
        product_id=product_id, offset=pagination.offset, limit=pagination.limit
    )
    return Page.build(items, total, pagination.page, pagination.limit)


@router.get("/low-stock", response_model=list[ProductRead], summary="Products needing reorder")
def low_stock_products(service: InventoryServiceDep) -> list[ProductRead]:
    return service.list_low_stock()


@router.get("/summary", summary="Inventory KPIs")
def inventory_summary(service: InventoryServiceDep) -> dict:
    return service.inventory_summary()