from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class Merchant(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    name: str = Field(max_length=200)
    external_ref: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Customer(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    name: str = Field(max_length=200)
    phone: str = Field(max_length=30, index=True)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Order(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    merchant_id: UUID = Field(foreign_key="merchant.id", index=True)
    customer_id: UUID = Field(foreign_key="customer.id", index=True)
    external_ref: str = Field(max_length=100, index=True)
    status: str = Field(default="created", max_length=30, index=True)
    currency: str = Field(default="NGN", max_length=3)
    total_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    cod_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class DeliveryJob(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    order_id: UUID = Field(foreign_key="order.id", index=True, unique=True)
    status: str = Field(default="pending", max_length=30, index=True)
    priority: str = Field(default="standard", max_length=20)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class Stop(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    sequence: int = Field(default=1)
    address_text: str = Field(max_length=500)
    landmark: Optional[str] = Field(default=None, max_length=300)
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    location_confidence: str = Field(default="unverified", max_length=20)
    recipient_available: Optional[bool] = Field(default=None)
    status: str = Field(default="pending", max_length=30, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class OrderCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: UUID
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str = Field(min_length=5, max_length=30)
    external_ref: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    total_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)
    cod_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)
    address_text: str = Field(min_length=1, max_length=500)
    landmark: Optional[str] = Field(default=None, max_length=300)
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    location_confidence: Literal["unverified", "geocoded", "customer_confirmed", "driver_confirmed"] = Field(default="unverified", max_length=20)
    plus_code: Optional[str] = Field(default=None, max_length=20)
    recipient_available: Optional[bool] = Field(default=None)
    service_zone_id: Optional[UUID] = Field(default=None)
    window_start: Optional[datetime] = Field(default=None)
    window_end: Optional[datetime] = Field(default=None)


class OrderRead(SQLModel):
    id: UUID
    tenant_id: UUID
    merchant_id: UUID
    customer_id: UUID
    external_ref: str
    status: str
    currency: str
    total_amount: Decimal
    cod_amount: Decimal
    # Money fields are serialized as decimal strings (pydantic v2 default) to keep precision.
    delivery_job_id: Optional[UUID] = None
    stop_id: Optional[UUID] = None
    stop_status: Optional[str] = None
    created_at: datetime
    customer_name: Optional[str] = None
    merchant_name: Optional[str] = None
    address_text: Optional[str] = None
    landmark: Optional[str] = None
    location_confidence: Optional[str] = None
    job_status: Optional[str] = None
    driver_id: Optional[UUID] = None
    driver_name: Optional[str] = None
    # Effective location = original stop overlaid with append-only corrections; the original is preserved.
    location_corrected: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_score: Optional[int] = None
    plus_code: Optional[str] = None
    recipient_available: Optional[bool] = None
    service_zone_id: Optional[UUID] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    tracking_token: Optional[str] = None
