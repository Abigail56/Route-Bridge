"""The Admin (the site's owner) lands straight on the Admin console: their company is made, or handed to them, on first sign-in."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from routebridge.auth.dependencies import get_optional_user
from routebridge.config.settings import get_settings
from routebridge.db.session import get_session
from routebridge.integrations.sessions import AuthUser
from routebridge.main import app
from routebridge.models.access import TenantMembership, User
from routebridge.models.core import Tenant

client = TestClient(app)
OWNER = "chukwuabigail307@gmail.com"


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch):
    """A site of its own (empty database), with sign-in on and nobody listed in PLATFORM_ADMIN_EMAILS."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    settings = get_settings()
    monkeypatch.setattr(settings, "require_auth", True)
    monkeypatch.setattr(settings, "platform_admin_emails", [])
    monkeypatch.setattr(settings, "platform_admin_subjects", [])
    monkeypatch.setattr(settings, "owner_email", OWNER)
    app.dependency_overrides[get_session] = session_override

    def person(subject: str, email: str, verified: bool = True):
        with Session(engine) as session:
            session.add(User(clerk_user_id=subject, email=email, email_verified=verified))
            session.commit()
        app.dependency_overrides[get_optional_user] = lambda: AuthUser(subject, {"email": email})

    yield engine, person
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_optional_user, None)


def owners(engine) -> list[tuple[str, str]]:
    with Session(engine) as session:
        rows = session.exec(select(Tenant.name, User.email).join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
                            .join(User, User.id == TenantMembership.user_id).where(TenantMembership.role == "tenant_owner")).all()
        return [tuple(row) for row in rows]


def test_the_owner_is_the_admin_without_any_setting_and_gets_routebridge_made(site):
    engine, person = site
    person("user_owner", OWNER)
    assert client.get("/api/v1/auth/me/profile").json()["is_platform_admin"] is True
    made = client.post("/api/v1/admin/my-workspace")
    assert made.status_code == 200 and made.json()["name"] == "RouteBridge"
    assert owners(engine) == [("RouteBridge", OWNER)]
    # signing in again does not make a second company
    assert client.post("/api/v1/admin/my-workspace").json()["id"] == made.json()["id"]
    assert [t["name"] for t in client.get("/api/v1/auth/me/tenants").json()] == ["RouteBridge"]


def test_the_only_company_with_no_owner_is_handed_to_the_admin(site):
    engine, person = site
    with Session(engine) as session:
        session.add(Tenant(name="Made Earlier"))
        session.commit()
    person("user_owner", OWNER)
    assert client.post("/api/v1/admin/my-workspace").json()["name"] == "Made Earlier"
    assert owners(engine) == [("Made Earlier", OWNER)]


def test_an_unproven_owner_email_or_anybody_else_gets_nothing(site):
    engine, person = site
    person("user_typed_it", OWNER, verified=False)  # typed the owner's address into the sign-up form, never proved it
    assert client.post("/api/v1/admin/my-workspace").status_code == 403
    person("user_someone", "someone@example.test")
    assert client.post("/api/v1/admin/my-workspace").status_code == 403
    assert owners(engine) == []


def test_with_several_companies_nothing_is_guessed(site):
    engine, person = site
    with Session(engine) as session:
        session.add(Tenant(name="One"))
        session.add(Tenant(name="Two"))
        session.commit()
    person("user_owner", OWNER)
    assert client.post("/api/v1/admin/my-workspace").status_code == 409
    assert owners(engine) == []
