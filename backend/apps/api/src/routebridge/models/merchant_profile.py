"""A shop's own registration details: where it is, who to ask for, and where its money is paid.

Kept apart from the Merchant row on purpose. The Merchant row is returned by several staff lists (dispatchers, riders' tools),
so bank details must never ride along with it. They are only read through routes that check the caller's role.
"""
import re
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import ConfigDict, field_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from routebridge.models.catalog import MerchantCreate, _check_email, _check_phone
from routebridge.models.core import utc_now

# every field the shop must give before it can place orders
REQUIRED_FIELDS = ("contact_phone", "address_line", "city", "state", "bank_name", "account_number", "account_name")


class MerchantProfile(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("merchant_id", name="uq_merchantprofile_merchant"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(foreign_key="tenant.id", index=True)
    merchant_id: UUID = Field(foreign_key="merchant.id", index=True)
    contact_person: Optional[str] = Field(default=None, max_length=200)
    address_line: Optional[str] = Field(default=None, max_length=300)
    landmark: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=120)
    bank_name: Optional[str] = Field(default=None, max_length=120)
    account_number: Optional[str] = Field(default=None, max_length=20)
    account_name: Optional[str] = Field(default=None, max_length=200)
    completed_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


def _clean(value: Optional[str]) -> Optional[str]:
    cleaned = " ".join((value or "").split())
    return cleaned or None


class MerchantRegister(MerchantCreate):
    """The owner adds a shop by the shop's own sign-in id (the id they see after signing up). The shop fills in the rest itself."""

    model_config = ConfigDict(extra="forbid")

    clerk_user_id: str = Field(min_length=3, max_length=200)

    @field_validator("clerk_user_id")
    @classmethod
    def _id(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3 or any(ch.isspace() for ch in value):
            raise ValueError("Paste the shop's user id exactly as they sent it (it starts with user_)")
        return value


class ProfileInput(SQLModel):
    """What a shop sends when it registers or updates its details."""

    model_config = ConfigDict(extra="forbid")

    contact_phone: str = Field(min_length=7, max_length=30)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    contact_person: Optional[str] = Field(default=None, max_length=200)
    address_line: str = Field(min_length=3, max_length=300)
    landmark: Optional[str] = Field(default=None, max_length=300)
    city: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=120)
    bank_name: str = Field(min_length=2, max_length=120)
    account_number: str = Field(min_length=10, max_length=16)  # spaces are allowed while typing; exactly 10 digits remain
    account_name: str = Field(min_length=2, max_length=200)

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        cleaned = _check_phone(value)
        if cleaned is None:
            raise ValueError("Enter a phone number such as +2348012345678")
        return cleaned

    @field_validator("contact_email")
    @classmethod
    def _email(cls, value: Optional[str]) -> Optional[str]:
        return _check_email(value) if value is not None else None

    @field_validator("account_number")
    @classmethod
    def _account(cls, value: str) -> str:
        digits = value.replace(" ", "").replace("-", "")
        if not re.fullmatch(r"\d{10}", digits):
            raise ValueError("A Nigerian bank account number is exactly 10 digits")
        return digits

    @field_validator("contact_person", "address_line", "landmark", "city", "state", "bank_name", "account_name")
    @classmethod
    def _text(cls, value: Optional[str]) -> Optional[str]:
        return _clean(value)


def is_complete(contact_phone: Optional[str], profile: Optional[MerchantProfile]) -> bool:
    """True when the shop has given everything it must give before placing orders."""
    if not contact_phone or profile is None:
        return False
    return all(getattr(profile, name) for name in REQUIRED_FIELDS if name != "contact_phone")


def mask_account(number: Optional[str]) -> Optional[str]:
    return None if not number else "******" + number[-4:]
