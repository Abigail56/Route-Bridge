from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from routebridge.models.core import utc_now

KINDS = ("dispute", "refund", "damage", "loss")
# open -> investigating -> approved | rejected, approved -> paid. Rejected and paid are final.
NEXT_STATUS = {"open": ("investigating", "approved", "rejected"), "investigating": ("approved", "rejected"), "approved": ("paid",), "rejected": (), "paid": ()}


class Claim(SQLModel, table=True):
    """A problem a shop (or staff on its behalf) raises about a delivery: a dispute, a refund, damaged or lost goods."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    merchant_id: UUID = Field(foreign_key="merchant.id", index=True)
    order_id: Optional[UUID] = Field(default=None, foreign_key="order.id", index=True)
    kind: str = Field(max_length=20)
    status: str = Field(default="open", max_length=20, index=True)
    raised_by: str = Field(default="merchant", max_length=20)  # merchant | staff
    description: str = Field(max_length=2000)
    amount_claimed: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    amount_approved: Optional[Decimal] = Field(default=None, max_digits=14, decimal_places=2)
    resolution_note: Optional[str] = Field(default=None, max_length=1000)  # the shop can read this
    internal_note: Optional[str] = Field(default=None, max_length=1000)  # staff only
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
    decided_at: Optional[datetime] = Field(default=None, index=True)
