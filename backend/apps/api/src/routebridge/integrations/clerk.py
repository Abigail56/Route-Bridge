from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, status

from routebridge.config.settings import get_settings


@dataclass(frozen=True)
class ClerkUser:
    subject: str
    claims: dict[str, Any]


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    settings = get_settings()
    if not settings.clerk_jwks_url:
        raise RuntimeError("ROUTEBRIDGE_CLERK_JWKS_URL is not configured")
    return jwt.PyJWKClient(settings.clerk_jwks_url)


def verify_clerk_token(token: str) -> ClerkUser:
    settings = get_settings()
    if not settings.clerk_jwks_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Clerk authentication is not configured")
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer or None,
            audience=settings.clerk_audience or None,
            options={"verify_aud": bool(settings.clerk_audience)},
        )
    except (jwt.PyJWTError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Clerk token") from exc
    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clerk token has no subject")
    return ClerkUser(subject=subject, claims=claims)
