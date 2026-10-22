from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class JoinRequest(SQLModel, table=True):
    """A person who signed up and pressed "Send to the Admin": they ask to be added as a shop or a Dispatcher (rider).
    One row per person and company; sending again refreshes it. It grants nothing: the owner still adds them by user id."""

    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_joinrequest_tenant_user"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    role: str = Field(max_length=20)  # merchant_user | driver
    shop_name: str | None = Field(default=None, max_length=120)
    status: str = Field(default="open", max_length=20, index=True)  # open | dismissed
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    sent_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
