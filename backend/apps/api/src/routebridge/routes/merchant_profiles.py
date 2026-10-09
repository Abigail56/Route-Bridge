"""Shop registration details.

Portal (the shop itself): read and fill in its own address, phone and bank account. The shop comes from the signed-in account,
never from the request, so one shop can never read or change another's details.
Staff: the owner and managers read every shop's details. Bank details go only to the roles that handle money.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Field, Session, SQLModel, select

from routebridge.auth.authorization import TenantPrincipal, merchant_portal, tenant_roles
from routebridge.db.session import get_session
from routebridge.models.merchant_profile import MerchantProfile, ProfileInput, is_complete
from routebridge.models.orders import Merchant
from routebridge.models.core import utc_now
from routebridge.services.events import record_event

staff = APIRouter(prefix="/tenants/{tenant_id}", tags=["merchant-profiles"])
portal = APIRouter(prefix="/tenants/{tenant_id}/portal", tags=["merchant-portal"])

STAFF_ROLES = ("tenant_owner", "tenant_admin", "operations_manager", "finance", "dispatcher")
BANK_ROLES = ("tenant_owner", "tenant_admin", "finance")  # who may read a shop's bank account


class ProfileRead(SQLModel):
    merchant_id: UUID
    merchant_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    contact_person: Optional[str] = None
    address_line: Optional[str] = None
    landmark: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    complete: bool = False
    bank_visible: bool = True
    updated_at: Optional[str] = None


def _read(merchant: Merchant, profile: Optional[MerchantProfile], show_bank: bool) -> ProfileRead:
    result = ProfileRead(
        merchant_id=merchant.id, merchant_name=merchant.name, contact_phone=merchant.contact_phone, contact_email=merchant.contact_email,
        complete=is_complete(merchant.contact_phone, profile), bank_visible=show_bank,
    )
    if profile is not None:
        result.contact_person, result.address_line, result.landmark = profile.contact_person, profile.address_line, profile.landmark
        result.city, result.state = profile.city, profile.state
        result.updated_at = profile.updated_at.isoformat() if profile.updated_at else None
        if show_bank:
            result.bank_name, result.account_number, result.account_name = profile.bank_name, profile.account_number, profile.account_name
    return result


def _profile_of(session: Session, merchant_id: UUID) -> Optional[MerchantProfile]:
    return session.exec(select(MerchantProfile).where(MerchantProfile.merchant_id == merchant_id)).first()


@staff.get("/merchant-profiles", response_model=list[ProfileRead])
def list_profiles(tenant_id: UUID, principal: TenantPrincipal = Depends(tenant_roles(*STAFF_ROLES)), session: Session = Depends(get_session)) -> list[ProfileRead]:
    """Every shop of this company with the details it has registered. Other companies' shops are never included."""
    show_bank = principal.role in BANK_ROLES
    merchants = session.exec(select(Merchant).where(Merchant.tenant_id == tenant_id).order_by(Merchant.name)).all()
    profiles = {p.merchant_id: p for p in session.exec(select(MerchantProfile).where(MerchantProfile.tenant_id == tenant_id)).all()}
    return [_read(m, profiles.get(m.id), show_bank) for m in merchants]


def _own_merchant(session: Session, tenant_id: UUID, principal: TenantPrincipal) -> Merchant:
    merchant = session.get(Merchant, principal.merchant_id)
    if merchant is None or merchant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Your account is linked to a merchant that no longer exists. Ask the company owner.")
    return merchant


@portal.get("/profile", response_model=ProfileRead)
def my_profile(tenant_id: UUID, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> ProfileRead:
    merchant = _own_merchant(session, tenant_id, principal)
    return _read(merchant, _profile_of(session, merchant.id), show_bank=True)


@portal.put("/profile", response_model=ProfileRead)
def save_my_profile(tenant_id: UUID, payload: ProfileInput, principal: TenantPrincipal = Depends(merchant_portal), session: Session = Depends(get_session)) -> ProfileRead:
    """Register (or update) the shop's details: phone, address and the bank account it is paid into."""
    merchant = _own_merchant(session, tenant_id, principal)
    merchant.contact_phone = payload.contact_phone
    if "contact_email" in payload.model_fields_set:
        merchant.contact_email = payload.contact_email or None
    profile = _profile_of(session, merchant.id) or MerchantProfile(tenant_id=tenant_id, merchant_id=merchant.id)
    first_time = profile.completed_at is None
    for name in ("contact_person", "address_line", "landmark", "city", "state", "bank_name", "account_number", "account_name"):
        setattr(profile, name, getattr(payload, name))
    profile.updated_at = utc_now()
    if first_time:
        profile.completed_at = profile.updated_at
    session.add(merchant)
    session.add(profile)
    session.flush()
    # field names only: the bank account itself never goes into the audit trail
    record_event(session, tenant_id, "merchant.registered" if first_time else "merchant.profile_updated", "merchant", merchant.id, {"by": "merchant"})
    session.commit()
    session.refresh(profile)
    return _read(merchant, profile, show_bank=True)
