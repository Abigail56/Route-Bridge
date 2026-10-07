from typing import Optional
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Country(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    iso_code: str = Field(index=True, max_length=2, unique=True)
    name: str = Field(max_length=100)
    default_currency: str = Field(default="NGN", max_length=3)
    default_timezone: str = Field(default="Africa/Lagos", max_length=64)
    status: str = Field(default="active", max_length=20)


class OperatingArea(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    country_id: UUID = Field(foreign_key="country.id", index=True)
    code: str = Field(index=True, max_length=40)
    name: str = Field(max_length=100)
    timezone: str = Field(default="Africa/Lagos", max_length=64)
    status: str = Field(default="active", max_length=20)


class Tenant(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=200)
    status: str = Field(default="active", max_length=20)
    auto_assign: bool = Field(default=False)  # give new orders to the nearest available driver straight away
    plan: str = Field(default="trial", max_length=20)
    plan_valid_until: Optional[datetime] = Field(default=None)  # None = no end date recorded (older workspaces)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class TenantArea(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    operating_area_id: UUID = Field(foreign_key="operatingarea.id", index=True)
    local_currency: str = Field(default="NGN", max_length=3)
    timezone: str = Field(default="Africa/Lagos", max_length=64)
    status: str = Field(default="active", max_length=20)


class HealthResponse(SQLModel):
    status: str
    service: str
    environment: str
