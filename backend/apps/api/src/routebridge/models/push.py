from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class PushSubscription(SQLModel, table=True):
    """One phone (browser) that agreed to receive alerts for a driver. The endpoint is the address the phone's push service gave us."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    driver_id: UUID = Field(foreign_key="driver.id", index=True)
    endpoint: str = Field(max_length=1000, unique=True, index=True)
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)
    failures: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    last_sent_at: Optional[datetime] = Field(default=None)
