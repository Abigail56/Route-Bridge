import re
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from pydantic import field_validator
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


PHONE_PATTERN = re.compile(r"^\+?[0-9 ()-]{7,30}$")


def _check_phone(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    if not PHONE_PATTERN.match(value.strip()):
        raise ValueError("Enter a phone number such as +2348012345678")
    return value.strip()


class MerchantCreate(SQLModel):
    name: str = Field(min_length=2, max_length=200)
    external_ref: Optional[str] = Field(default=None, max_length=100)
    contact_phone: Optional[str] = Field(default=None, max_length=30)
    contact_email: Optional[str] = Field(default=None, max_length=320)

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, value: Optional[str]) -> Optional[str]:
        return _check_phone(value)


class MerchantUpdate(SQLModel):
    contact_phone: Optional[str] = Field(default=None, max_length=30)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    notify_orders: Optional[bool] = None

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, value: Optional[str]) -> Optional[str]:
        return _check_phone(value)


class ServiceZoneCreate(SQLModel):
    operating_area_id: UUID
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=120)
