from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from routebridge.auth.authorization import require_tenant_access
from routebridge.db.session import engine
from routebridge.integrations.clerk import ClerkUser
from routebridge.models.access import TenantMembership, User
from routebridge.models.core import Tenant
from routebridge.services.clerk_sync import sync_clerk_user


def test_clerk_user_sync_creates_user_and_membership_from_public_metadata() -> None:
    tenant_id = uuid4()
    with Session(engine) as session:
        session.add(Tenant(id=tenant_id, name="Sync Tenant", status="active"))
        user = sync_clerk_user(session, {"id": f"clerk_{uuid4()}", "first_name": "Ada", "last_name": "Okafor", "email_addresses": [{"email_address": "ada@example.test"}], "public_metadata": {"tenant_id": str(tenant_id), "role": "dispatcher"}})
        session.commit()
        membership = session.exec(select(TenantMembership).where(TenantMembership.user_id == user.id, TenantMembership.tenant_id == tenant_id)).one()
        assert user.full_name == "Ada Okafor"
        assert membership.role == "dispatcher"


def test_cross_tenant_access_is_rejected() -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    with Session(engine) as session:
        session.add(Tenant(id=tenant_id, name="Tenant A", status="active"))
        session.add(Tenant(id=other_tenant_id, name="Tenant B", status="active"))
        user = sync_clerk_user(session, {"id": f"clerk_{uuid4()}", "public_metadata": {"tenant_id": str(tenant_id), "role": "dispatcher"}})
        session.commit()
        with pytest.raises(HTTPException) as exc:
            require_tenant_access(other_tenant_id, session, ClerkUser(user.clerk_user_id, {}))
        assert exc.value.status_code == 403
