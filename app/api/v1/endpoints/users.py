from typing import Annotated, Optional

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import PaginationDep, UserServiceDep
from app.schemas.common import Page
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserRead], summary="List users")
def list_users(
    service: UserServiceDep,
    pagination: PaginationDep,
    search: Annotated[Optional[str], Query(description="Match name or email")] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
) -> Page[UserRead]:
    items, total = service.list_users(
        offset=pagination.offset,
        limit=pagination.limit,
        search=search,
        is_active=is_active,
    )
    return Page.build(items, total, pagination.page, pagination.limit)


@router.post(
    "", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Create a user"
)
def create_user(payload: UserCreate, service: UserServiceDep) -> UserRead:
    return service.create_user(payload)


@router.get("/{user_id}", response_model=UserRead, summary="Get one user")
def get_user(
    service: UserServiceDep,
    user_id: Annotated[int, Path(ge=1)],
) -> UserRead:
    return service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user")
def update_user(
    payload: UserUpdate,
    service: UserServiceDep,
    user_id: Annotated[int, Path(ge=1)],
) -> UserRead:
    return service.update_user(user_id, payload)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserRead,
    summary="Deactivate a user",
)
def deactivate_user(
    service: UserServiceDep,
    user_id: Annotated[int, Path(ge=1)],
) -> UserRead:
    return service.deactivate_user(user_id)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user",
)
def delete_user(
    service: UserServiceDep,
    user_id: Annotated[int, Path(ge=1)],
) -> Response:
    service.delete_user(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)