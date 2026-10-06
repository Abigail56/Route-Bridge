from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class ServiceZone(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    operating_area_id: UUID = Field(foreign_key="operatingarea.id", index=True)
    code: str = Field(max_length=50, index=True)
    name: str = Field(max_length=120)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class RateCard(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    service_zone_id: UUID = Field(foreign_key="servicezone.id", index=True)
    name: str = Field(max_length=120)
    currency: str = Field(default="NGN", max_length=3)
    base_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    cod_fee: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class TenantCreate(SQLModel):
    name: str = Field(min_length=2, max_length=200)


class TenantRead(SQLModel):
    id: UUID
    name: str
    status: str
    created_at: datetime


class MerchantCreate(SQLModel):
    name: str = Field(min_length=2, max_length=200)
    external_ref: Optional[str] = Field(default=None, max_length=100)


class ServiceZoneCreate(SQLModel):
    operating_area_id: UUID
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=120)
