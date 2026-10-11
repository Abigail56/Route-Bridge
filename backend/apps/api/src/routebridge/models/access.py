from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


ROLES = {"tenant_owner", "tenant_admin", "dispatcher", "operations_manager", "finance", "merchant_user", "partner_operator", "read_only", "driver"}


# The only roles the owner can give to someone new. "tenant_owner" (shown as Admin) is the workspace's single top role, a shop's login
# is made by Add merchant, and the "driver" role is what the console calls a Dispatcher: the rider who sees only their own orders.
# The other ROLES stay valid so people added before this change keep working; they simply can no longer be handed out.
ASSIGNABLE_ROLES = {"driver", "merchant_user"}


class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    clerk_user_id: str = Field(max_length=200, unique=True, index=True)
    email: str | None = Field(default=None, max_length=320, index=True)
    full_name: str | None = Field(default=None, max_length=200)
    status: str = Field(default="active", max_length=20, index=True)
    # what a Dispatcher (rider) registers about themselves before the Admin adds them by user id
    phone: str | None = Field(default=None, max_length=30)
    photo: str | None = Field(default=None, max_length=60000)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class TenantMembership(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenantmembership_tenant_user"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    role: str = Field(default="read_only", max_length=40, index=True)
    status: str = Field(default="active", max_length=20, index=True)
    merchant_id: UUID | None = Field(default=None, index=True)
    # a Dispatcher (role "driver") is tied to one rider record, which holds their phone, Staff/Contracted type and assigned jobs
    driver_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
