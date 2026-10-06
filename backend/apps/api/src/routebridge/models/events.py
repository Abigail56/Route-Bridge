from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class OutboxEvent(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    event_type: str = Field(max_length=120, index=True)
    aggregate_type: str = Field(max_length=80, index=True)
    aggregate_id: UUID = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", max_length=20, index=True)
    attempts: int = Field(default=0)
    available_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    published_at: datetime | None = Field(default=None)
    last_error: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


class LiveEvent(SQLModel):
    id: str
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime
