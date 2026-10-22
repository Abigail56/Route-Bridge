from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.integrations.sessions import AuthUser, token_from_request, verify_session_token
from routebridge.models.access import User


def _check_still_valid(session: Session, user: AuthUser) -> AuthUser:
    """A signature is not enough: the account must still exist, be active, and not have ended its sessions since."""
    row = session.exec(select(User).where(User.clerk_user_id == user.subject)).first()
    if row is None or row.status != "active" or row.session_version != user.claims.get("ver", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session ended. Sign in again.")
    return user


def get_current_user(request: Request, session: Annotated[Session, Depends(get_session)]) -> AuthUser:
    token = token_from_request(request)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return _check_still_valid(session, verify_session_token(token))


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]


def get_optional_user(request: Request, session: Annotated[Session, Depends(get_session)]) -> AuthUser | None:
    token = token_from_request(request)
    if token is None:
        return None
    try:
        return _check_still_valid(session, verify_session_token(token))
    except HTTPException:
        settings = get_settings()
        # Local development without enforced sign-in: a stale cookie (say, from before a restart) means "signed out", not an error.
        if settings.environment in {"development", "test"} and not settings.require_auth:
            return None
        raise
