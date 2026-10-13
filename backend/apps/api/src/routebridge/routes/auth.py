from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from routebridge.auth.dependencies import CurrentUser, get_optional_user
from routebridge.db.session import get_session
from routebridge.integrations.clerk import ClerkUser
from routebridge.services.platform import is_platform_admin
from routebridge.models.access import TenantMembership, User
from routebridge.models.core import Tenant
from routebridge.models.orders import Merchant
from routebridge.config.settings import get_settings
from routebridge.integrations.rate_limit import enforce_auth_attempt

router = APIRouter(prefix="/Auth", tags=["Authentication"])


class AuthAttemptRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)


class AuthAttemptResponse(BaseModel):
    allowed: bool
    provider: str = "clerk"
    message: str


def _attempt_key(kind: str, request: Request, identifier: str) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    return f"auth:{kind}:{ip}:{identifier.strip().lower()}"


def _allow(kind: str, body: AuthAttemptRequest, request: Request) -> AuthAttemptResponse:
    settings = get_settings()
    enforce_auth_attempt(_attempt_key(kind, request, body.identifier), settings.auth_attempt_limit, settings.auth_attempt_window_seconds)
    return AuthAttemptResponse(allowed=True, message=f"{kind.title()} attempt allowed; continue with Clerk.")


@router.post("/signup", response_model=AuthAttemptResponse)
def signup_attempt(body: AuthAttemptRequest, request: Request) -> AuthAttemptResponse:
    return _allow("signup", body, request)


@router.post("/signin", response_model=AuthAttemptResponse)
def signin_attempt(body: AuthAttemptRequest, request: Request) -> AuthAttemptResponse:
    return _allow("signin", body, request)


@router.get("/me")
def current_user(user: CurrentUser) -> dict[str, object]:
    return {"subject": user.subject, "claims": user.claims}


class MyTenant(BaseModel):
    tenant_id: UUID
    name: str
    role: str
    merchant_id: UUID | None = None
    merchant_name: str | None = None


def _dev_bypass() -> bool:
    settings = get_settings()
    return settings.environment in {"development", "test"} and not settings.require_clerk_auth


def _ensure_user(session: Session, clerk_user: ClerkUser) -> User:
    """Provision the RouteBridge user on first sight of a verified Clerk identity.

    Clerk's user.created webhook normally does this, but it cannot reach a laptop and can lag in production, so the
    first authenticated request is enough. A user row grants no access by itself: tenant access still needs a
    membership. Deactivated users stay blocked.
    """
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user.subject)).first()
    if user is None:
        claims = clerk_user.claims
        full_name = claims.get("name") or " ".join(p for p in (claims.get("first_name"), claims.get("last_name")) if p) or None
        user = User(clerk_user_id=clerk_user.subject, email=claims.get("email"), full_name=full_name)
        session.add(user)
        session.commit()
        session.refresh(user)
    if user.status != "active":
        raise HTTPException(status_code=403, detail="This account has been deactivated")
    return user


def _tenants_for(session: Session, user: User) -> list[MyTenant]:
    rows = session.exec(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == user.id, TenantMembership.status == "active")
    ).all()
    out = []
    for m, t in rows:
        if t.status != "active":
            continue
        merchant = session.get(Merchant, m.merchant_id) if m.merchant_id else None
        out.append(MyTenant(tenant_id=t.id, name=t.name, role=m.role, merchant_id=m.merchant_id, merchant_name=merchant.name if merchant else None))
    return out


def _is_platform_admin(session: Session, clerk_user: ClerkUser | None) -> bool:
    if clerk_user is None:
        return _dev_bypass()  # local development without Clerk: everyone may set up a workspace
    return is_platform_admin(session, clerk_user.subject)


@router.get("/me/tenants", response_model=list[MyTenant])
def my_tenants(
    session: Annotated[Session, Depends(get_session)],
    clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)],
) -> list[MyTenant]:
    """Tenants the caller belongs to, so the frontend does not need a build-time tenant id."""
    if clerk_user is None:
        if _dev_bypass():
            return [MyTenant(tenant_id=t.id, name=t.name, role="dev") for t in session.exec(select(Tenant).where(Tenant.status == "active")).all()]
        raise HTTPException(status_code=401, detail="Clerk authentication required")
    return _tenants_for(session, _ensure_user(session, clerk_user))


class Profile(BaseModel):
    subject: str | None
    email: str | None = None
    name: str | None = None
    is_platform_admin: bool
    tenants: list[MyTenant]


@router.get("/me/profile", response_model=Profile)
def my_profile(
    session: Annotated[Session, Depends(get_session)],
    clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)],
) -> Profile:
    """Who is signed in, whether they may create workspaces, and which workspaces they belong to.

    A signed-in user with no workspaces gets an empty list (not an error) so the console can show first-run setup.
    """
    if clerk_user is None:
        if not _dev_bypass():
            raise HTTPException(status_code=401, detail="Clerk authentication required")
        tenants = [MyTenant(tenant_id=t.id, name=t.name, role="dev") for t in session.exec(select(Tenant).where(Tenant.status == "active")).all()]
        return Profile(subject=None, is_platform_admin=True, tenants=tenants)
    user = _ensure_user(session, clerk_user)
    return Profile(subject=user.clerk_user_id, email=user.email, name=user.full_name, is_platform_admin=_is_platform_admin(session, clerk_user), tenants=_tenants_for(session, user))


class RiderRegistration(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=7, max_length=30)
    photo: str | None = Field(default=None, max_length=80000)  # a small JPEG/PNG/WebP data URL; left out = keep the one saved


class RiderRegistrationRead(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    photo: str | None = None
    complete: bool = False


def _rider_read(user: User) -> RiderRegistrationRead:
    return RiderRegistrationRead(full_name=user.full_name, email=user.email, phone=user.phone, photo=user.photo, complete=bool(user.full_name and user.phone and user.photo))


@router.get("/me/rider-registration", response_model=RiderRegistrationRead)
def my_rider_registration(session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)]) -> RiderRegistrationRead:
    if clerk_user is None:
        raise HTTPException(status_code=401, detail="Clerk authentication required")
    return _rider_read(_ensure_user(session, clerk_user))


@router.put("/me/rider-registration", response_model=RiderRegistrationRead)
def save_my_rider_registration(payload: RiderRegistration, session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)]) -> RiderRegistrationRead:
    """A future Dispatcher registers their own name, phone number and picture. The sign-in email and password are Clerk's.
    The Admin then adds them with just their user id and these details come along."""
    from routebridge.models.catalog import _check_phone
    from routebridge.routes.driver import check_photo

    if clerk_user is None:
        raise HTTPException(status_code=401, detail="Clerk authentication required")

    try:
        phone = _check_phone(payload.phone)
    except ValueError:
        phone = None
    if phone is None:
        raise HTTPException(status_code=422, detail="Enter a phone number such as +2348012345678")
    user = _ensure_user(session, clerk_user)
    user.full_name = " ".join(payload.full_name.split())
    user.phone = phone
    if payload.photo is not None:
        user.photo = check_photo(payload.photo)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _rider_read(user)
