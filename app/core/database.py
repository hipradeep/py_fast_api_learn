from collections.abc import Generator

from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine: Engine = create_engine(
    settings.database_url,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

# Disposes the connection pool instead of pooling it. Used by tests / scripts.
null_engine: Engine = create_engine(
    settings.database_url,
    echo=settings.DB_ECHO,
    poolclass=NullPool,
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Yields a session that commits when the request succeeds and rolls back
    when it raises, so each request is one transaction."""
    session = Session(engine)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    else:
        session.commit()
    finally:
        session.close()