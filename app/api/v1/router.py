from fastapi import APIRouter

from app.api.v1.endpoints import health, inventory, orders, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(inventory.router)
api_router.include_router(orders.router)

__all__ = ["api_router"]