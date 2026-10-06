from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from routebridge.auth.authorization import require_tenant_access
from routebridge.config.settings import get_settings
from routebridge.db.session import engine
from routebridge.integrations.rate_limit import enforce_auth_attempt
from routebridge.routes.webhooks import receive_webhook
from routebridge.models.core import Tenant


def test_production_tenant_access_requires_clerk_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "require_clerk_auth", True)
    with Session(engine) as session:
        tenant_id = uuid4()
        session.add(Tenant(id=tenant_id, name="Production Guard", status="active"))
        session.commit()
        with pytest.raises(HTTPException) as exc:
            require_tenant_access(tenant_id, session, None)
        assert exc.value.status_code == 401


def test_production_rate_limit_requires_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "redis_url", "")
    with pytest.raises(HTTPException) as exc:
        enforce_auth_attempt(f"guard-{uuid4()}", 5, 60)
    assert exc.value.status_code == 503
