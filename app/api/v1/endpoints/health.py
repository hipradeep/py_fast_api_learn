from typing import Literal

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health() -> dict:
    return {"status": "ok", "app": settings.PROJECT_NAME, "version": settings.VERSION}


@router.get("/health/ready", summary="Readiness probe including database connectivity")
def readiness(session: SessionDep) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}


@router.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "message": f"{settings.PROJECT_NAME} is running",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "api": settings.API_V1_PREFIX,
    }