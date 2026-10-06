from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, event
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


def _default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


class AuditEvent(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    event_type: str = Field(max_length=100, index=True)
    aggregate_type: str = Field(max_length=50, index=True)
    aggregate_id: UUID = Field(index=True)
    actor_type: str = Field(default="system", max_length=30)
    actor_id: Optional[UUID] = Field(default=None, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    occurred_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _audit_is_append_only(*_: object) -> None:
    raise RuntimeError("AuditEvent rows are append-only and cannot be updated or deleted")


class IdempotencyRecord(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    key: str = Field(max_length=200, index=True)
    request_hash: str = Field(max_length=64)
    response_json: str = Field(max_length=100000)
    response_status: int = Field(default=201)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    expires_at: datetime = Field(default_factory=_default_expiry, nullable=False, index=True)


class MobileSyncEvent(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    event_id: UUID = Field(index=True)
    device_id: str = Field(max_length=150, index=True)
    event_type: str = Field(max_length=100, index=True)
    aggregate_type: str = Field(max_length=50)
    aggregate_id: UUID = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    occurred_at: datetime = Field(default_factory=utc_now, nullable=False)
    received_at: datetime = Field(default_factory=utc_now, nullable=False)


class MobileSyncEventInput(SQLModel):
    event_id: UUID
    device_id: str = Field(min_length=1, max_length=150)
    event_type: str = Field(min_length=1, max_length=100)
    aggregate_type: str = Field(min_length=1, max_length=50)
    aggregate_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)


class MobileSyncRequest(SQLModel):
    events: list[MobileSyncEventInput] = Field(max_length=100)


class MobileSyncResponse(SQLModel):
    accepted_event_ids: list[UUID]
    duplicate_event_ids: list[UUID]
    rejected_event_ids: list[UUID]
