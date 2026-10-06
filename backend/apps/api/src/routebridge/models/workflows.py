from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class Notification(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    order_id: Optional[UUID] = Field(default=None, foreign_key="order.id", index=True)
    channel: str = Field(max_length=20)
    recipient: str = Field(max_length=200)
    template: str = Field(max_length=100)
    status: str = Field(default="queued", max_length=20, index=True)
    provider_message_id: Optional[str] = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    sent_at: Optional[datetime] = Field(default=None)


class ReconciliationResolve(SQLModel):
    resolution_note: str = Field(min_length=2, max_length=1000)


class ReconciliationRead(SQLModel):
    id: UUID
    payment_id: UUID
    status: str
    variance_amount: Decimal
    resolution_note: Optional[str]
    created_at: datetime
