from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.models.access import ROLES, TenantMembership, User
from routebridge.models.core import Tenant
from routebridge.integrations.clerk import ClerkUser


class TenantPrincipal:
    def __init__(self, user: User | None, membership: TenantMembership | None, clerk_user: ClerkUser | None):
        self.user = user
        self.membership = membership
        self.clerk_user = clerk_user

    @property
    def role(self) -> str | None:
        return self.membership.role if self.membership else None

    @property
    def merchant_id(self) -> UUID | None:
        return self.membership.merchant_id if self.membership else None


def require_tenant_access(tenant_id: UUID, session: Session, clerk_user: ClerkUser | None, allowed_roles: set[str] | None = None) -> TenantPrincipal:
    settings = get_settings()
    if clerk_user is None:
        if settings.environment in {"development", "test"} and not settings.require_clerk_auth:
            return TenantPrincipal(None, None, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clerk authentication required")
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user.subject, User.status == "active")).first()
    if user is None:
        raise HTTPException(status_code=403, detail="RouteBridge user is not provisioned")
    tenant = session.get(Tenant, tenant_id)
    if tenant is not None and tenant.status != "active":
        raise HTTPException(status_code=403, detail="This workspace is suspended. Contact RouteBridge support.")
    membership = session.exec(select(TenantMembership).where(TenantMembership.user_id == user.id, TenantMembership.tenant_id == tenant_id, TenantMembership.status == "active")).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="User is not a member of this tenant")
    if allowed_roles and membership.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Role is not permitted for this operation")
    return TenantPrincipal(user, membership, clerk_user)


def tenant_member(tenant_id: UUID, session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)]) -> TenantPrincipal:
    principal = require_tenant_access(tenant_id, session, clerk_user)
    if principal.role == "merchant_user":
        # A merchant's staff may only use the merchant portal. Every general route that answers "any member" must refuse them,
        # otherwise they could read the whole company's orders and reports.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Merchant accounts use the merchant portal")
    return principal


def merchant_portal(tenant_id: UUID, session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)]) -> TenantPrincipal:
    """Only a merchant user who is linked to one merchant of this company. Everything in the portal is scoped to that merchant."""
    principal = require_tenant_access(tenant_id, session, clerk_user, {"merchant_user"})
    if principal.merchant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is not linked to a merchant yet. Ask the company owner to link it.")
    return principal


def tenant_roles(*roles: str):
    invalid = set(roles) - ROLES
    if invalid:
        raise ValueError(f"Unknown roles: {sorted(invalid)}")
    def dependency(tenant_id: UUID, session: Annotated[Session, Depends(get_session)], clerk_user: Annotated[ClerkUser | None, Depends(get_optional_user)]) -> TenantPrincipal:
        return require_tenant_access(tenant_id, session, clerk_user, set(roles))
    return dependency

TenantMember = Annotated[TenantPrincipal, Depends(tenant_member)]
