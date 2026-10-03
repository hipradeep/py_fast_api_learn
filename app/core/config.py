from functools import lru_cache
from typing import List

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "py_fast_api_learn"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Users, Orders and Inventory system built with FastAPI + SQLModel"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "1234"
    POSTGRES_DB: str = "py_crud"

    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800

    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()