from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from routebridge.config.settings import get_settings
from routebridge.integrations.clerk import ClerkUser, verify_clerk_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> ClerkUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    return verify_clerk_token(credentials.credentials)


CurrentUser = Annotated[ClerkUser, Depends(get_current_user)]


def get_optional_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> ClerkUser | None:
    if credentials is None:
        return None
    settings = get_settings()
    # Local dev without Clerk configured: ignore a token the frontend may send instead of failing with 503.
    if not settings.clerk_jwks_url and settings.environment in {"development", "test"} and not settings.require_clerk_auth:
        return None
    return verify_clerk_token(credentials.credentials)
