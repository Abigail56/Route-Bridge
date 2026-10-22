import hashlib
import logging
from datetime import timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from routebridge.auth.dependencies import CurrentUser, get_optional_user
from routebridge.db.session import get_session
from routebridge.integrations import google_oauth
from routebridge.integrations.sessions import (AuthUser, clear_session_cookie, issue_session_token, new_subject, set_session_cookie,
                                               token_from_request, verify_session_token)
from routebridge.services.passwords import hash_password, needs_rehash, password_problem, verify_password
from routebridge.services.platform import is_platform_admin
from routebridge.models.access import TenantMembership, User
from routebridge.models.core import Tenant, utc_now
from routebridge.models.orders import Merchant
from routebridge.services.driver_zones import clean_zone_names, split_zone_names
from routebridge.config.settings import get_settings
from routebridge.integrations.rate_limit import enforce_auth_attempt

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

OAUTH_COOKIE = "rb_oauth"
RESET_AUDIENCE = "routebridge-reset"
OAUTH_AUDIENCE = "routebridge-oauth"
RESET_MINUTES = 30


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _limit(kind: str, request: Request, identifier: str = "") -> None:
    settings = get_settings()
    enforce_auth_attempt(f"auth:{kind}:{_client_ip(request)}:{identifier.strip().lower()}", settings.auth_attempt_limit, settings.auth_attempt_window_seconds)


def _secret() -> str:
    from routebridge.integrations.sessions import _secret as session_secret

    return session_secret()


def _clean_email(value: str) -> str:
    email = value.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or any(ch.isspace() for ch in email) or len(email) > 320:
        raise HTTPException(status_code=422, detail="Enter a valid email address, such as ada@example.com")
    return email


def _by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(func.lower(User.email) == email)).first()


def _clean_next(value: str | None) -> str:
    """Only a path on our own website: never another site (an open redirect would make phishing links look like ours)."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


class SessionInfo(BaseModel):
    signed_in: bool
    subject: str | None = None
    email: str | None = None
    name: str | None = None
    started_at: int | None = None  # seconds since 1970: the website counts the fixed session length from here
    remember: bool = False  # "Keep me signed in on this device": the website then skips its 12-hour and idle sign-outs


def _start_session(response: Response, user: User, remember: bool = False) -> SessionInfo:
    kept = remember and get_settings().session_remember_days > 0
    set_session_cookie(response, issue_session_token(user.clerk_user_id, user.email, user.full_name, user.session_version, remember=kept), remember=kept)
    return SessionInfo(signed_in=True, subject=user.clerk_user_id, email=user.email, name=user.full_name, started_at=int(utc_now().timestamp()), remember=kept)


class Providers(BaseModel):
    google: bool
    password_reset: bool
    remember_days: int = 0  # 0 = no "Keep me signed in" box


@router.get("/providers", response_model=Providers)
def providers() -> Providers:
    """What the sign-in page can offer on this server."""
    settings = get_settings()
    return Providers(google=settings.google_enabled, password_reset=bool(settings.resend_api_key) or settings.environment in {"development", "test"},
                     remember_days=max(settings.session_remember_days, 0))


class PersonDetails(BaseModel):
    """Where a person is and how to reach them: asked at sign-up, and once after a Google sign-up (Google gives only name and email)."""

    phone: str = Field(min_length=7, max_length=30)
    country: str = Field(min_length=2, max_length=2)  # ISO code, e.g. NG
    state: str = Field(min_length=2, max_length=100)
    region: str = Field(min_length=2, max_length=120)  # city, LGA or area


def _apply_details(user: User, details: PersonDetails) -> None:
    from routebridge.models.catalog import _check_phone

    try:
        phone = _check_phone(details.phone)
    except ValueError:
        phone = None
    if phone is None:
        raise HTTPException(status_code=422, detail="Enter a phone number such as +2348012345678")
    country = details.country.strip().upper()
    if len(country) != 2 or not country.isalpha():
        raise HTTPException(status_code=422, detail="Choose your country")
    user.phone = phone
    user.country = country
    user.state = " ".join(details.state.split())
    user.region = " ".join(details.region.split())


def details_complete(user: User) -> bool:
    return bool(user.phone and user.country and user.state and user.region)


class RegisterRequest(PersonDetails):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1000)
    full_name: str = Field(min_length=2, max_length=200)


@router.post("/register", response_model=SessionInfo, status_code=201)
def register(body: RegisterRequest, request: Request, response: Response, session: Annotated[Session, Depends(get_session)]) -> SessionInfo:
    _limit("register", request)
    email = _clean_email(body.email)
    problem = password_problem(body.password, email)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if _by_email(session, email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead, or use Forgot password.")
    user = User(clerk_user_id=new_subject(), email=email, full_name=" ".join(body.full_name.split()), password_hash=hash_password(body.password))
    _apply_details(user, body)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _start_session(response, user)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1000)
    remember: bool = False  # "Keep me signed in on this device"


@router.post("/login", response_model=SessionInfo)
def login(body: LoginRequest, request: Request, response: Response, session: Annotated[Session, Depends(get_session)]) -> SessionInfo:
    email = body.email.strip().lower()
    _limit("login", request, email)
    # the address in the key above comes from a header a client can fake, so each account also has its own limit
    settings = get_settings()
    enforce_auth_attempt(f"auth:login-account:{email}", settings.auth_attempt_limit * 4, settings.auth_attempt_window_seconds)
    user = _by_email(session, email)
    # the same answer for an unknown email and a wrong password, and the same work (verify_password checks a dummy hash)
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        if user is not None and user.password_hash is None and user.google_sub:
            raise HTTPException(status_code=401, detail="This account signs in with Google. Use Continue with Google.")
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="This account has been deactivated")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        session.add(user)
        session.commit()
    return _start_session(response, user, remember=body.remember)


@router.post("/logout", response_model=SessionInfo)
def logout(request: Request, response: Response, session: Annotated[Session, Depends(get_session)], everywhere: bool = False) -> SessionInfo:
    """Sign out here; with ?everywhere=true also end this account's sessions on every other device."""
    token = token_from_request(request)
    if everywhere and token:
        try:
            subject = verify_session_token(token).subject
        except HTTPException:
            subject = None
        user = session.exec(select(User).where(User.clerk_user_id == subject)).first() if subject else None
        if user is not None:
            user.session_version += 1
            session.add(user)
            session.commit()
    clear_session_cookie(response)
    return SessionInfo(signed_in=False)


@router.get("/session", response_model=SessionInfo)
def current_session(request: Request, response: Response, session: Annotated[Session, Depends(get_session)]) -> SessionInfo:
    """Who is signed in, for the website. Never 401: an ended or broken session just reads as signed out (and its cookie is cleared)."""
    response.headers["Cache-Control"] = "no-store"
    try:
        user = get_optional_user(request, session)
    except HTTPException:
        user = None
    if user is None:
        if token_from_request(request):
            clear_session_cookie(response)
        return SessionInfo(signed_in=False)
    row = session.exec(select(User).where(User.clerk_user_id == user.subject)).first()
    started = user.claims.get("iat")
    return SessionInfo(signed_in=True, subject=user.subject, email=row.email if row else None, name=row.full_name if row else None, started_at=int(started) if started else None,
                       remember=bool(user.claims.get("rem")))


# ---- forgotten password ----------------------------------------------------------------------------------------


def _password_fingerprint(user: User) -> str:
    # part of the reset token: once the password changes, every earlier reset link stops working
    return hashlib.sha256((user.password_hash or "none").encode()).hexdigest()[:16]


class ForgotRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


@router.post("/password/forgot", status_code=202)
def forgot_password(body: ForgotRequest, request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    """Emails a reset link valid for 30 minutes. Answers the same whether or not the email has an account."""
    from routebridge.providers import LogEmailProvider, get_email_provider

    email = body.email.strip().lower()
    _limit("forgot", request, email)
    answer = {"status": "If an account exists for that email, a reset link is on its way."}
    user = _by_email(session, email)
    if user is None or user.status != "active":
        return answer
    settings = get_settings()
    now = utc_now()
    token = jwt.encode({"sub": user.clerk_user_id, "pwf": _password_fingerprint(user), "aud": RESET_AUDIENCE, "iat": now, "exp": now + timedelta(minutes=RESET_MINUTES)}, _secret(), algorithm="HS256")
    link = f"{settings.web_base_url}/reset-password#token={token}"
    provider = get_email_provider()
    if isinstance(provider, LogEmailProvider) and settings.environment not in {"development", "test"}:
        logger.warning("password reset asked for, but no email sender is configured (ROUTEBRIDGE_RESEND_API_KEY); nothing sent")
        return answer
    body_text = (f"Someone asked to reset the password for your RouteBridge account ({email}).\n\n"
                 f"Choose a new password here (the link works for {RESET_MINUTES} minutes, once):\n{link}\n\n"
                 "If this was not you, ignore this email: your password stays as it is.")
    try:
        provider.send(email, body_text, subject="Reset your RouteBridge password")
    except Exception:
        logger.exception("could not send the password reset email")
    if isinstance(provider, LogEmailProvider):
        logger.info("[dev] password reset link for %s: %s", email, link)
    return answer


class ResetRequest(BaseModel):
    token: str = Field(min_length=10, max_length=2000)
    password: str = Field(min_length=1, max_length=1000)


@router.post("/password/reset", response_model=SessionInfo)
def reset_password(body: ResetRequest, request: Request, response: Response, session: Annotated[Session, Depends(get_session)]) -> SessionInfo:
    _limit("reset", request)
    expired = HTTPException(status_code=400, detail="This reset link has expired or was already used. Ask for a new one.")
    try:
        claims = jwt.decode(body.token, _secret(), algorithms=["HS256"], audience=RESET_AUDIENCE)
    except jwt.PyJWTError as exc:
        raise expired from exc
    user = session.exec(select(User).where(User.clerk_user_id == claims.get("sub"))).first()
    if user is None or user.status != "active" or claims.get("pwf") != _password_fingerprint(user):
        raise expired
    problem = password_problem(body.password, user.email)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    user.password_hash = hash_password(body.password)
    user.email_verified = True  # they opened a link sent to that address
    user.session_version += 1  # every other session (perhaps someone else's) ends
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    session.refresh(user)
    return _start_session(response, user)


# ---- Continue with Google --------------------------------------------------------------------------------------


@router.get("/google/start")
def google_start(next: str | None = None, remember: bool = False) -> RedirectResponse:
    settings = get_settings()
    if not settings.google_enabled:
        return RedirectResponse(f"{settings.web_base_url}/sign-in?error=google_off", status_code=303)
    attempt = google_oauth.new_attempt()
    now = utc_now()
    packed = jwt.encode({"st": attempt.state, "cv": attempt.verifier, "nn": attempt.nonce, "nx": _clean_next(next), "rm": bool(remember), "aud": OAUTH_AUDIENCE,
                         "iat": now, "exp": now + timedelta(minutes=10)}, _secret(), algorithm="HS256")
    response = RedirectResponse(google_oauth.authorize_url(attempt), status_code=303)
    response.set_cookie(OAUTH_COOKIE, packed, max_age=600, httponly=True, secure=settings.web_base_url.startswith("https://"), samesite="lax", path="/api/v1/auth/google")
    return response


def _google_user(session: Session, account: google_oauth.GoogleAccount) -> User:
    user = session.exec(select(User).where(User.google_sub == account.sub)).first()
    if user is None:
        user = _by_email(session, account.email)
        if user is None:
            user = User(clerk_user_id=new_subject(), email=account.email, full_name=account.name)
        elif not user.email_verified:
            # The password account with this address never proved it owned the address; Google just did. Whoever set that
            # password may not be this person, so it stops working (and its sessions end). The owner can set a new one by reset.
            user.password_hash = None
            user.session_version += 1
        user.google_sub = account.sub
    user.email_verified = True
    if not user.full_name and account.name:
        user.full_name = account.name
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.get("/google/callback")
def google_callback(request: Request, session: Annotated[Session, Depends(get_session)], code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    settings = get_settings()

    def back(problem: str) -> RedirectResponse:
        response = RedirectResponse(f"{settings.web_base_url}/sign-in?error={problem}", status_code=303)
        response.delete_cookie(OAUTH_COOKIE, path="/api/v1/auth/google")
        return response

    if error or not code or not state:
        return back("google_cancelled")
    try:
        packed = jwt.decode(request.cookies.get(OAUTH_COOKIE, ""), _secret(), algorithms=["HS256"], audience=OAUTH_AUDIENCE)
    except jwt.PyJWTError:
        return back("google_expired")
    if packed.get("st") != state:
        return back("google_expired")
    try:
        account = google_oauth.exchange_code(code, google_oauth.Attempt(packed["st"], packed["cv"], packed["nn"]))
    except google_oauth.GoogleSignInError as exc:
        logger.warning("Google sign-in failed: %s", exc)
        return back("google_failed")
    if not account.email_verified:
        return back("google_unverified")
    _limit("google", request, account.email)
    user = _google_user(session, account)
    if user.status != "active":
        return back("deactivated")
    response = RedirectResponse(f"{settings.web_base_url}{_clean_next(packed.get('nx'))}", status_code=303)
    response.delete_cookie(OAUTH_COOKIE, path="/api/v1/auth/google")
    kept = bool(packed.get("rm")) and settings.session_remember_days > 0
    set_session_cookie(response, issue_session_token(user.clerk_user_id, user.email, user.full_name, user.session_version, remember=kept), remember=kept)
    return response


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
    return settings.environment in {"development", "test"} and not settings.require_auth


def _ensure_user(session: Session, clerk_user: AuthUser) -> User:
    """The user row behind a session. Sign-up creates it; this still makes one for a session without a row (tests sign
    people in that way). A user row grants no access by itself: tenant access still needs a membership. Deactivated users stay blocked.
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


def _is_platform_admin(session: Session, clerk_user: AuthUser | None) -> bool:
    if clerk_user is None:
        return _dev_bypass()  # local development without sign-in: everyone may set up a workspace
    return is_platform_admin(session, clerk_user.subject)


@router.get("/me/tenants", response_model=list[MyTenant])
def my_tenants(
    session: Annotated[Session, Depends(get_session)],
    clerk_user: Annotated[AuthUser | None, Depends(get_optional_user)],
) -> list[MyTenant]:
    """Tenants the caller belongs to, so the frontend does not need a build-time tenant id."""
    if clerk_user is None:
        if _dev_bypass():
            return [MyTenant(tenant_id=t.id, name=t.name, role="dev") for t in session.exec(select(Tenant).where(Tenant.status == "active")).all()]
        raise HTTPException(status_code=401, detail="Sign in required")
    return _tenants_for(session, _ensure_user(session, clerk_user))


class Profile(BaseModel):
    subject: str | None
    email: str | None = None
    name: str | None = None
    phone: str | None = None
    country: str | None = None
    state: str | None = None
    region: str | None = None
    details_complete: bool = True
    is_platform_admin: bool
    tenants: list[MyTenant]


@router.get("/me/profile", response_model=Profile)
def my_profile(
    session: Annotated[Session, Depends(get_session)],
    clerk_user: Annotated[AuthUser | None, Depends(get_optional_user)],
) -> Profile:
    """Who is signed in, whether they may create workspaces, and which workspaces they belong to.

    A signed-in user with no workspaces gets an empty list (not an error) so the console can show first-run setup.
    """
    if clerk_user is None:
        if not _dev_bypass():
            raise HTTPException(status_code=401, detail="Sign in required")
        tenants = [MyTenant(tenant_id=t.id, name=t.name, role="dev") for t in session.exec(select(Tenant).where(Tenant.status == "active")).all()]
        return Profile(subject=None, is_platform_admin=True, tenants=tenants)
    user = _ensure_user(session, clerk_user)
    return Profile(subject=user.clerk_user_id, email=user.email, name=user.full_name, phone=user.phone, country=user.country, state=user.state, region=user.region,
                   details_complete=details_complete(user), is_platform_admin=_is_platform_admin(session, clerk_user), tenants=_tenants_for(session, user))


class MyDetails(PersonDetails):
    full_name: str = Field(min_length=2, max_length=200)


@router.put("/me/details", response_model=Profile)
def save_my_details(payload: MyDetails, session: Annotated[Session, Depends(get_session)], clerk_user: CurrentUser) -> Profile:
    """The signed-in person fills in or changes their name, phone, country, state and region."""
    user = _ensure_user(session, clerk_user)
    user.full_name = " ".join(payload.full_name.split())
    _apply_details(user, payload)
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    return my_profile(session, clerk_user)


class RiderRegistration(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=7, max_length=30)
    photo: str | None = Field(default=None, max_length=80000)  # a small JPEG/PNG/WebP data URL; left out = keep the one saved
    # the areas they can deliver in ("Lagos", "Ibadan"); the Admin's zones with the same names become theirs when they are added
    zones: list[str] = Field(min_length=1, max_length=10)


class RiderRegistrationRead(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    photo: str | None = None
    zones: list[str] = []
    complete: bool = False


def _rider_read(user: User) -> RiderRegistrationRead:
    zones = split_zone_names(user.rider_zones)
    return RiderRegistrationRead(full_name=user.full_name, email=user.email, phone=user.phone, photo=user.photo, zones=zones, complete=bool(user.full_name and user.phone and user.photo and zones))


@router.get("/me/rider-registration", response_model=RiderRegistrationRead)
def my_rider_registration(session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[AuthUser | None, Depends(get_optional_user)]) -> RiderRegistrationRead:
    if clerk_user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return _rider_read(_ensure_user(session, clerk_user))


@router.put("/me/rider-registration", response_model=RiderRegistrationRead)
def save_my_rider_registration(payload: RiderRegistration, session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[AuthUser | None, Depends(get_optional_user)]) -> RiderRegistrationRead:
    """A future Dispatcher registers their own name, phone number, picture and the areas they deliver in. The sign-in email and password are their account's.
    The Admin then adds them with just their user id and these details come along."""
    from routebridge.models.catalog import _check_phone
    from routebridge.routes.driver import check_photo

    if clerk_user is None:
        raise HTTPException(status_code=401, detail="Sign in required")

    try:
        phone = _check_phone(payload.phone)
    except ValueError:
        phone = None
    if phone is None:
        raise HTTPException(status_code=422, detail="Enter a phone number such as +2348012345678")
    zones = clean_zone_names(payload.zones)
    if not zones or any(len(z) > 80 for z in zones):
        raise HTTPException(status_code=422, detail="Enter at least one area you deliver in, such as Lagos")
    user = _ensure_user(session, clerk_user)
    user.full_name = " ".join(payload.full_name.split())
    user.phone = phone
    user.rider_zones = ", ".join(zones)
    if payload.photo is not None:
        user.photo = check_photo(payload.photo)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _rider_read(user)
