from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from routebridge.models.access import ROLES, TenantMembership, User
from routebridge.models.core import Tenant


def _metadata(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("public_metadata") or data.get("publicMetadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def sync_clerk_user(session: Session, data: dict[str, Any]) -> User:
    clerk_user_id = str(data.get("id") or data.get("user_id") or "")
    if not clerk_user_id:
        raise ValueError("Clerk user payload has no id")
    emails = data.get("email_addresses") or data.get("emailAddresses") or []
    email = None
    if emails and isinstance(emails[0], dict):
        email = emails[0].get("email_address") or emails[0].get("emailAddress")
    full_name = " ".join(part for part in [data.get("first_name") or data.get("firstName"), data.get("last_name") or data.get("lastName")] if part) or None
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).first()
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(clerk_user_id=clerk_user_id, email=email, full_name=full_name)
        session.add(user)
        session.flush()
    else:
        user.email = email or user.email
        user.full_name = full_name or user.full_name
        user.updated_at = now
        user.status = "active"
    metadata = _metadata(data)
    tenant_id = metadata.get("tenant_id")
    role = metadata.get("role", "read_only")
    if tenant_id and role in ROLES:
        try:
            tenant_uuid = UUID(str(tenant_id))
        except ValueError:
            tenant_uuid = None
        if tenant_uuid and session.get(Tenant, tenant_uuid):
            membership = session.exec(select(TenantMembership).where(TenantMembership.tenant_id == tenant_uuid, TenantMembership.user_id == user.id)).first()
            if membership is None:
                session.add(TenantMembership(tenant_id=tenant_uuid, user_id=user.id, role=role))
            else:
                membership.role = role
                membership.status = "active"
                membership.updated_at = now
    return user


def deactivate_clerk_user(session: Session, clerk_user_id: str) -> None:
    user = session.exec(select(User).where(User.clerk_user_id == clerk_user_id)).first()
    if user:
        user.status = "inactive"
        user.updated_at = datetime.now(timezone.utc)
        memberships = session.exec(select(TenantMembership).where(TenantMembership.user_id == user.id)).all()
        for membership in memberships:
            membership.status = "inactive"
            membership.updated_at = datetime.now(timezone.utc)
