from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from routebridge.auth.authorization import require_tenant_access
from routebridge.db.session import engine
from routebridge.integrations.sessions import AuthUser
from routebridge.models.access import TenantMembership, User
from routebridge.models.core import Tenant


def test_cross_tenant_access_is_rejected() -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    with Session(engine) as session:
        session.add(Tenant(id=tenant_id, name="Tenant A", status="active"))
        session.add(Tenant(id=other_tenant_id, name="Tenant B", status="active"))
        user = User(clerk_user_id=f"user_{uuid4().hex[:12]}")
        session.add(user)
        session.flush()
        session.add(TenantMembership(tenant_id=tenant_id, user_id=user.id, role="dispatcher"))
        session.commit()
        with pytest.raises(HTTPException) as exc:
            require_tenant_access(other_tenant_id, session, AuthUser(user.clerk_user_id, {}))
        assert exc.value.status_code == 403
