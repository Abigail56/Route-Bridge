"""RouteBridge's own sign-in sessions (no outside sign-in service).

A session is an HS256 token signed with ROUTEBRIDGE_SESSION_SECRET. The website keeps it in an httpOnly cookie the page's
scripts cannot read; scripts and tests may send the same token as `Authorization: Bearer`. The token carries the user's
`session_version`: raising it (sign out everywhere, password reset, deactivation) ends every session issued before.
"""
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, Response, status

from routebridge.config.settings import get_settings
from routebridge.models.core import utc_now

logger = logging.getLogger(__name__)

SESSION_COOKIE = "rb_session"
AUDIENCE = "routebridge-session"


@dataclass(frozen=True)
class AuthUser:
    """Who a verified session belongs to: `subject` is the user id people see and send (user_...)."""

    subject: str
    claims: dict[str, Any]


@lru_cache(maxsize=1)
def _dev_secret() -> str:
    logger.warning("ROUTEBRIDGE_SESSION_SECRET is not set: using a random one, so every restart signs everybody out")
    return secrets.token_urlsafe(48)


def _secret() -> str:
    secret = get_settings().session_secret
    if secret:
        return secret
    if get_settings().environment in {"development", "test"}:
        return _dev_secret()
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sign-in is not configured on this server")


def new_subject() -> str:
    return "user_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]


def session_length(remember: bool = False) -> timedelta:
    """A normal session lasts SESSION_MAX_HOURS. "Keep me signed in on this device" makes it SESSION_REMEMBER_DAYS (when that is above 0)."""
    settings = get_settings()
    if remember and settings.session_remember_days > 0:
        return timedelta(days=settings.session_remember_days)
    return timedelta(hours=settings.session_max_hours)


def issue_session_token(subject: str, email: str | None, name: str | None, version: int, remember: bool = False) -> str:
    now = utc_now()
    kept = remember and get_settings().session_remember_days > 0
    claims = {"sub": subject, "email": email, "name": name, "ver": version, "typ": "session", "aud": AUDIENCE, "iat": now,
              "exp": now + session_length(kept), **({"rem": True} if kept else {})}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def verify_session_token(token: str) -> AuthUser:
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"], audience=AUDIENCE, leeway=30)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    if claims.get("typ") != "session" or not claims.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return AuthUser(subject=claims["sub"], claims=claims)


def token_from_request(request: Request) -> str | None:
    """The bearer token if one was sent, else the session cookie."""
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip() or None
    return request.cookies.get(SESSION_COOKIE) or None


def _secure() -> bool:
    return get_settings().web_base_url.startswith("https://")


def set_session_cookie(response: Response, token: str, remember: bool = False) -> None:
    # Lax: sent when someone follows a link to the site (and on the Google redirect back), never on another site's form posts
    response.set_cookie(SESSION_COOKIE, token, max_age=int(session_length(remember).total_seconds()), httponly=True, secure=_secure(), samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=_secure(), samesite="lax")
