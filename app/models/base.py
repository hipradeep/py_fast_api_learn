from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=utc_now, nullable=False, index=True, sa_column_kwargs={}
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        nullable=False,
        sa_column_kwargs={"onupdate": utc_now},
    )