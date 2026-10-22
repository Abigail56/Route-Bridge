"""RouteBridge's own sign-in: Argon2id passwords, session cookies, password reset by email and Continue with Google."""
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations import google_oauth
from routebridge.integrations.sessions import SESSION_COOKIE
from routebridge.main import app
from routebridge.models.access import User
from routebridge.services.platform import is_platform_admin

create_db_and_tables()


def fresh_client() -> TestClient:
    # a different address per client, so the per-address sign-up limit never trips across tests
    return TestClient(app, headers={"x-forwarded-for": f"10.{uuid4().int % 250}.{uuid4().int % 250}.{uuid4().int % 250}"})


def email() -> str:
    return f"person-{uuid4().hex[:10]}@example.test"


DETAILS = {"phone": "+2348012345678", "country": "NG", "state": "Lagos", "region": "Ikeja"}


def register(client: TestClient, address: str, password: str = "a good long password", name: str = "Ada Obi"):
    return client.post("/api/v1/auth/register", json={"email": address, "password": password, "full_name": name, **DETAILS})


def user_by_email(address: str) -> User:
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == address.lower())).one()


def test_sign_up_stores_an_argon2id_hash_and_signs_in_with_an_httponly_cookie() -> None:
    client, address = fresh_client(), email()
    response = register(client, address)
    assert response.status_code == 201, response.text
    assert response.json()["signed_in"] and response.json()["subject"].startswith("user_")
    cookie = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert user_by_email(address).password_hash.startswith("$argon2id$")
    assert "a good long password" not in user_by_email(address).password_hash
    session = client.get("/api/v1/auth/session").json()
    assert session["signed_in"] and session["email"] == address
    assert client.get("/api/v1/auth/me/profile").json()["subject"] == response.json()["subject"]


def test_sign_up_keeps_where_the_person_is_and_needs_all_of_it() -> None:
    client, address = fresh_client(), email()
    assert register(client, address).status_code == 201
    profile = client.get("/api/v1/auth/me/profile").json()
    assert (profile["phone"], profile["country"], profile["state"], profile["region"], profile["details_complete"]) == ("+2348012345678", "NG", "Lagos", "Ikeja", True)
    for missing in DETAILS:
        body = {"email": email(), "password": "a good long password", "full_name": "Ada Obi", **{k: v for k, v in DETAILS.items() if k != missing}}
        assert fresh_client().post("/api/v1/auth/register", json=body).status_code == 422, missing
    bad_phone = {"email": email(), "password": "a good long password", "full_name": "Ada Obi", **DETAILS, "phone": "call me"}
    assert fresh_client().post("/api/v1/auth/register", json=bad_phone).status_code == 422


def test_an_email_is_registered_once_whatever_its_case() -> None:
    client, address = fresh_client(), email()
    assert register(client, address).status_code == 201
    again = register(fresh_client(), address.upper())
    assert again.status_code == 409 and "already exists" in again.json()["detail"]


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_weak_or_absurd_passwords_are_refused(password: str) -> None:
    assert register(fresh_client(), email(), password=password).status_code == 422


def test_sign_in_checks_the_password_and_says_the_same_for_an_unknown_email() -> None:
    address = email()
    register(fresh_client(), address)
    client = fresh_client()
    wrong = client.post("/api/v1/auth/login", json={"email": address, "password": "not the password"})
    unknown = client.post("/api/v1/auth/login", json={"email": email(), "password": "not the password"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
    right = client.post("/api/v1/auth/login", json={"email": address.upper(), "password": "a good long password"})
    assert right.status_code == 200 and client.get("/api/v1/auth/session").json()["signed_in"]


def test_sign_out_clears_the_cookie_and_everywhere_ends_every_other_session() -> None:
    address = email()
    first = fresh_client()
    register(first, address)
    stolen = first.cookies.get(SESSION_COOKIE)
    second = fresh_client()
    second.post("/api/v1/auth/login", json={"email": address, "password": "a good long password"})
    assert second.post("/api/v1/auth/logout?everywhere=true").json()["signed_in"] is False
    assert second.get("/api/v1/auth/session").json()["signed_in"] is False
    # the first device's token was issued before "everywhere": it no longer works, even sent as a bearer token
    other = fresh_client()
    assert other.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {stolen}"}).json()["signed_in"] is False


def test_a_deactivated_account_cannot_use_its_session_or_sign_in() -> None:
    address = email()
    client = fresh_client()
    register(client, address)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == address)).one()
        user.status = "inactive"
        session.add(user)
        session.commit()
    assert client.get("/api/v1/auth/session").json()["signed_in"] is False
    assert fresh_client().post("/api/v1/auth/login", json={"email": address, "password": "a good long password"}).status_code == 403


def test_a_forged_session_is_not_accepted() -> None:
    forged = jwt.encode({"sub": "user_someone", "typ": "session", "aud": "routebridge-session", "ver": 0, "exp": int(time.time()) + 600}, "guessed-secret", algorithm="HS256")
    assert fresh_client().get("/api/v1/auth/session", headers={"Authorization": f"Bearer {forged}"}).json()["signed_in"] is False


class Outbox:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, recipient: str, body: str, subject: str = "") -> str:
        self.sent.append((recipient, body))
        return "test"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    box = Outbox()
    monkeypatch.setattr("routebridge.providers.get_email_provider", lambda: box)
    return box


def reset_token(body: str) -> str:
    return body.split("#token=")[1].split()[0]


def test_forgot_password_emails_a_link_that_works_once_and_ends_other_sessions(outbox: Outbox) -> None:
    address = email()
    old_device = fresh_client()
    register(old_device, address)
    client = fresh_client()
    assert client.post("/api/v1/auth/password/forgot", json={"email": address}).status_code == 202
    assert client.post("/api/v1/auth/password/forgot", json={"email": email()}).status_code == 202  # unknown: same answer, nothing sent
    assert len(outbox.sent) == 1 and outbox.sent[0][0] == address
    token = reset_token(outbox.sent[0][1])
    reset = client.post("/api/v1/auth/password/reset", json={"token": token, "password": "a brand new password"})
    assert reset.status_code == 200 and reset.json()["signed_in"]
    assert user_by_email(address).email_verified is True
    assert old_device.get("/api/v1/auth/session").json()["signed_in"] is False
    assert client.post("/api/v1/auth/password/reset", json={"token": token, "password": "yet another password"}).status_code == 400
    assert fresh_client().post("/api/v1/auth/login", json={"email": address, "password": "a brand new password"}).status_code == 200


# ---- Continue with Google --------------------------------------------------------------------------------------


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "client-123.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    accounts: dict[str, google_oauth.GoogleAccount] = {}
    monkeypatch.setattr(google_oauth, "exchange_code", lambda code, attempt, client=None: accounts[code])
    return accounts


def google_round_trip(client: TestClient, account: google_oauth.GoogleAccount, next_path: str = "/orders"):
    start = client.get(f"/api/v1/auth/google/start?next={next_path}", follow_redirects=False)
    assert start.status_code == 303
    to_google = urlparse(start.headers["location"])
    query = parse_qs(to_google.query)
    assert to_google.netloc == "accounts.google.com" and query["code_challenge_method"] == ["S256"] and query["nonce"]
    code = f"code-{uuid4().hex}"
    google_round_trip.accounts[code] = account
    return client.get(f"/api/v1/auth/google/callback?code={code}&state={query['state'][0]}", follow_redirects=False)


def test_continue_with_google_creates_one_account_and_returns_to_the_page(google) -> None:
    google_round_trip.accounts = google
    address = email()
    account = google_oauth.GoogleAccount(sub=f"g-{uuid4().hex}", email=address, email_verified=True, name="Chi Eze")
    client = fresh_client()
    back = google_round_trip(client, account)
    assert back.status_code == 303 and back.headers["location"] == f"{get_settings().web_base_url}/orders"
    assert client.get("/api/v1/auth/session").json()["email"] == address
    again = fresh_client()
    google_round_trip(again, account)
    assert again.get("/api/v1/auth/session").json()["subject"] == client.get("/api/v1/auth/session").json()["subject"]
    user = user_by_email(address)
    assert user.email_verified and user.password_hash is None and user.google_sub == account.sub
    # Google gives only name and email: the rest is asked once, then saved
    assert client.get("/api/v1/auth/me/profile").json()["details_complete"] is False
    saved = client.put("/api/v1/auth/me/details", json={"full_name": "Chi Eze", **DETAILS, "state": "Abuja (FCT)", "region": "Garki"})
    assert saved.status_code == 200 and saved.json()["details_complete"] and saved.json()["state"] == "Abuja (FCT)"
    assert fresh_client().put("/api/v1/auth/me/details", json={"full_name": "Nobody", **DETAILS}).status_code == 401


def test_google_never_redirects_to_another_site(google) -> None:
    google_round_trip.accounts = google
    account = google_oauth.GoogleAccount(sub=f"g-{uuid4().hex}", email=email(), email_verified=True, name=None)
    back = google_round_trip(fresh_client(), account, next_path="//evil.example/steal")
    assert back.headers["location"] == f"{get_settings().web_base_url}/"


def test_a_callback_without_the_matching_start_is_refused(google) -> None:
    google["code-x"] = google_oauth.GoogleAccount(sub="g-x", email=email(), email_verified=True, name=None)
    back = fresh_client().get("/api/v1/auth/google/callback?code=code-x&state=made-up", follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"].endswith("/sign-in?error=google_expired")


def test_google_takes_over_a_password_account_nobody_proved_and_stops_that_password(google) -> None:
    google_round_trip.accounts = google
    address = email()
    squatter = fresh_client()
    register(squatter, address, password="the squatter knows this")  # someone typed this address before its owner arrived
    owner = fresh_client()
    google_round_trip(owner, google_oauth.GoogleAccount(sub=f"g-{uuid4().hex}", email=address, email_verified=True, name="Real Owner"))
    assert owner.get("/api/v1/auth/session").json()["signed_in"]
    assert squatter.get("/api/v1/auth/session").json()["signed_in"] is False
    assert fresh_client().post("/api/v1/auth/login", json={"email": address, "password": "the squatter knows this"}).status_code == 401


def test_an_unverified_google_email_is_refused(google) -> None:
    google_round_trip.accounts = google
    back = google_round_trip(fresh_client(), google_oauth.GoogleAccount(sub=f"g-{uuid4().hex}", email=email(), email_verified=False, name=None))
    assert back.headers["location"].endswith("/sign-in?error=google_unverified")


def test_google_id_tokens_are_checked_for_signature_audience_and_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", "client-123")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())

    def token(**changes) -> str:
        claims = {"iss": "https://accounts.google.com", "aud": "client-123", "sub": "g-1", "email": "Ada@Example.test", "email_verified": True, "nonce": "n-1", "iat": now, "exp": now + 300}
        return jwt.encode({**claims, **changes}, key, algorithm="RS256")

    account = google_oauth.verify_id_token(token(), "n-1", key=key.public_key())
    assert account.email == "ada@example.test" and account.email_verified
    for bad in (token(aud="someone-else"), token(nonce="n-2"), token(iss="https://evil.example"), token(exp=now - 3600)):
        with pytest.raises(google_oauth.GoogleSignInError):
            google_oauth.verify_id_token(bad, "n-1", key=key.public_key())
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(google_oauth.GoogleSignInError):
        google_oauth.verify_id_token(token(), "n-1", key=other_key.public_key())


def test_an_admin_email_only_counts_once_it_is_proven(monkeypatch: pytest.MonkeyPatch, google) -> None:
    google_round_trip.accounts = google
    address = email()
    monkeypatch.setattr(get_settings(), "platform_admin_emails", [address])
    impostor = fresh_client()
    subject = register(impostor, address).json()["subject"]
    with Session(engine) as session:
        assert is_platform_admin(session, subject) is False
    google_round_trip(fresh_client(), google_oauth.GoogleAccount(sub=f"g-{uuid4().hex}", email=address, email_verified=True, name="Admin"))
    with Session(engine) as session:
        assert is_platform_admin(session, subject) is True  # same account, now proven by Google (and the typed password is gone)


def test_the_front_page_reads_the_real_shop_plans_without_signing_in() -> None:
    from routebridge.config.plans import SHOP_PLANS

    answer = TestClient(app).get("/api/v1/public/plans/shops")
    assert answer.status_code == 200
    body = answer.json()
    assert body["trial_days"] == 14 and [p["key"] for p in body["plans"]] == ["trial", "basic", "standard", "pro"]
    assert {p["key"]: p["price_ngn"] for p in body["plans"]} == {k: v.price_ngn for k, v in SHOP_PLANS.items()}
