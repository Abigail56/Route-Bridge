from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now


class BillingPayment(SQLModel, table=True):
    """One attempt to pay for a plan. `reference` is ours and unique; Paystack echoes it back so a payment can never be applied twice."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    reference: str = Field(max_length=100, unique=True, index=True)
    provider: str = Field(default="paystack", max_length=20)
    plan: str = Field(max_length=20)
    amount_kobo: int = Field(default=0)
    currency: str = Field(default="NGN", max_length=3)
    status: str = Field(default="pending", max_length=20, index=True)  # pending | success | failed
    payer_email: Optional[str] = Field(default=None, max_length=320)
    # set when a SHOP paid for its own plan (empty for the company's plan)
    merchant_id: Optional[UUID] = Field(default=None, foreign_key="merchant.id", index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    paid_at: Optional[datetime] = Field(default=None)


class MerchantPlan(SQLModel, table=True):
    """A shop's own plan. Made the first time the shop (or the Admin) looks at billing, starting a free trial."""

    merchant_id: UUID = Field(foreign_key="merchant.id", primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    plan: str = Field(default="trial", max_length=20)
    valid_until: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
