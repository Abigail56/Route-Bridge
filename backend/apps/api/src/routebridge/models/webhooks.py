from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class WebhookReceipt(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider: str = Field(max_length=80, index=True)
    event_id: str = Field(max_length=200, index=True)
    payload_hash: str = Field(max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="accepted", max_length=30, index=True)
    received_at: datetime = Field(default_factory=utc_now, nullable=False)
    processed_at: datetime | None = Field(default=None)


class WebhookAccepted(SQLModel):
    status: str
    provider: str
    event_id: str
    duplicate: bool
