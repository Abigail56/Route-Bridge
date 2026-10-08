"""Delivery planning, location history, public tracking, OTP and consent tables.

These are separate tables (not extra columns on Order/Stop) so the original order data is never mutated
by later planning, correction or customer-contact activity.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class JobPlan(SQLModel, table=True):
    """Dispatch planning attributes of a delivery job: zone, delivery window and plus code."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True, unique=True)
    service_zone_id: Optional[UUID] = Field(default=None, foreign_key="servicezone.id", index=True)
    window_start: Optional[datetime] = Field(default=None, index=True)
    window_end: Optional[datetime] = Field(default=None, index=True)
    plus_code: Optional[str] = Field(default=None, max_length=20)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class StopCorrection(SQLModel, table=True):
    """Append-only location correction. The original Stop row is never modified."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    stop_id: UUID = Field(foreign_key="stop.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    source: str = Field(max_length=20)  # operator | driver | customer
    address_text: Optional[str] = Field(default=None, max_length=500)
    landmark: Optional[str] = Field(default=None, max_length=300)
    delivery_notes: Optional[str] = Field(default=None, max_length=1000)
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    plus_code: Optional[str] = Field(default=None, max_length=20)
    recipient_available: Optional[bool] = Field(default=None)
    location_confidence: Optional[str] = Field(default=None, max_length=20)
    reason: Optional[str] = Field(default=None, max_length=300)
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


class TrackingToken(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    token: str = Field(max_length=64, unique=True, index=True)
    expires_at: datetime = Field(nullable=False)
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class DeliveryOtp(SQLModel, table=True):
    """Server-issued delivery OTP. Only a hash is stored; proof of delivery requires `verified_at`."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    delivery_job_id: UUID = Field(foreign_key="deliveryjob.id", index=True)
    code_hash: str = Field(max_length=64)
    expires_at: datetime = Field(nullable=False)
    attempts: int = Field(default=0)
    verified_at: Optional[datetime] = Field(default=None)
    # only when staff pass the code on by hand (ROUTEBRIDGE_OTP_DELIVERY=dashboard): the code is kept just until it is used, replaced or expires
    relay_code: Optional[str] = Field(default=None, max_length=12)
    relayed_at: Optional[datetime] = Field(default=None)
    relayed_by: Optional[UUID] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class NotificationDelivery(SQLModel, table=True):
    """Rendered message body + retry state for a queued Notification (body is wiped after sending)."""

    notification_id: UUID = Field(foreign_key="notification.id", primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    body: str = Field(max_length=1000)
    attempts: int = Field(default=0)
    last_error: Optional[str] = Field(default=None, max_length=500)
    next_attempt_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


class ConsentRecord(SQLModel, table=True):
    """Customer consent / lawful-basis record for messaging and location use (NDPA)."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    customer_id: UUID = Field(foreign_key="customer.id", index=True)
    purpose: str = Field(max_length=40)  # sms | whatsapp | location
    granted: bool = Field(default=True)
    lawful_basis: str = Field(default="consent", max_length=30)
    recorded_at: datetime = Field(default_factory=utc_now, nullable=False)
