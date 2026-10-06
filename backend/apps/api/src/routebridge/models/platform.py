from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, event
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class PlatformAdmin(SQLModel, table=True):
    """A RouteBridge staff member who runs the whole platform (not a customer workspace)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    clerk_user_id: str = Field(max_length=200, unique=True, index=True)
    email: Optional[str] = Field(default=None, max_length=320)
    full_name: Optional[str] = Field(default=None, max_length=200)
    added_by: Optional[str] = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class PlatformAuditEvent(SQLModel, table=True):
    """Append-only record of platform-level actions (workspaces, admins, user changes)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor: str = Field(max_length=200, index=True)
    action: str = Field(max_length=100, index=True)
    target_type: str = Field(max_length=50)
    target_id: str = Field(max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    occurred_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


@event.listens_for(PlatformAuditEvent, "before_update")
@event.listens_for(PlatformAuditEvent, "before_delete")
def _platform_audit_is_append_only(*_: object) -> None:
    raise ValueError("Platform audit events are append-only")
