from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class Driver(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    name: str = Field(max_length=200)
    phone: str = Field(max_length=30, index=True)
    fleet_type: str = Field(default="contracted", max_length=20)
    status: str = Field(default="available", max_length=20, index=True)
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    last_location_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class DriverAssignment(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    driver_id: UUID = Field(foreign_key="driver.id", index=True)
    status: str = Field(default="active", max_length=20)
    assigned_at: datetime = Field(default_factory=utc_now, nullable=False)
    unassigned_at: Optional[datetime] = Field(default=None)


class DeliveryAttempt(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    attempt_number: int = Field(default=1)
    status: str = Field(default="started", max_length=30)
    reason_code: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=1000)
    occurred_at: datetime = Field(default_factory=utc_now, nullable=False)


class ProofOfDelivery(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    attempt_id: UUID = Field(foreign_key="deliveryattempt.id", index=True)
    otp_verified: bool = Field(default=False)
    photo_url: Optional[str] = Field(default=None, max_length=1000)
    signature_url: Optional[str] = Field(default=None, max_length=1000)
    recipient_name: Optional[str] = Field(default=None, max_length=200)
    captured_at: datetime = Field(default_factory=utc_now, nullable=False)


class PaymentRecord(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    order_id: UUID = Field(foreign_key="order.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    method: str = Field(default="cod", max_length=20)
    expected_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    collected_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    currency: str = Field(default="NGN", max_length=3)
    provider_reference: Optional[str] = Field(default=None, max_length=150, index=True)
    reconciliation_status: str = Field(default="pending", max_length=20, index=True)
    recorded_at: datetime = Field(default_factory=utc_now, nullable=False)


class ReconciliationItem(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    payment_id: UUID = Field(foreign_key="paymentrecord.id", index=True)
    status: str = Field(default="open", max_length=20)
    variance_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    resolution_note: Optional[str] = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class DriverCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=5, max_length=30)
    fleet_type: Literal["owned", "contracted", "partner"] = Field(default="contracted", max_length=20)


class AssignmentCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: UUID


class DeliveryTransition(SQLModel):
    model_config = ConfigDict(extra="forbid")

    target_status: str = Field(min_length=1, max_length=30)
    reason_code: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=1000)


class ProofCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    otp_verified: bool = False
    photo_url: Optional[str] = Field(default=None, max_length=1000)
    signature_url: Optional[str] = Field(default=None, max_length=1000)
    recipient_name: Optional[str] = Field(default=None, max_length=200)


class PaymentCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    method: str = Field(default="cod", max_length=20)
    collected_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    provider_reference: Optional[str] = Field(default=None, max_length=150)
