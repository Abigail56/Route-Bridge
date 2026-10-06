"""Short-lived HS256 tokens for driver devices (separate from Clerk operator sessions)."""
from datetime import timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.models.core import utc_now
from routebridge.models.operations import Driver

_bearer = HTTPBearer(auto_error=False)
AUDIENCE = "routebridge-driver"


def _secret() -> str:
    secret = get_settings().driver_token_secret
    if not secret or len(secret) < 16:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Driver tokens are not configured")
    return secret


def issue_driver_token(driver: Driver) -> tuple[str, int]:
    ttl = get_settings().driver_token_ttl_minutes
    now = utc_now()
    token = jwt.encode(
        {"sub": str(driver.id), "tid": str(driver.tenant_id), "typ": "driver", "aud": AUDIENCE, "iat": now, "exp": now + timedelta(minutes=ttl)},
        _secret(),
        algorithm="HS256",
    )
    return token, ttl * 60


def driver_principal(
    tenant_id: UUID,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Driver:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Driver token required")
    try:
        claims = jwt.decode(credentials.credentials, _secret(), algorithms=["HS256"], audience=AUDIENCE)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired driver token") from exc
    if claims.get("typ") != "driver" or claims.get("tid") != str(tenant_id):
        raise HTTPException(status_code=403, detail="Token is not valid for this tenant")
    driver = session.get(Driver, UUID(claims["sub"]))
    if driver is None or driver.tenant_id != tenant_id or driver.status == "offline":
        raise HTTPException(status_code=403, detail="Driver is not active")
    return driver
