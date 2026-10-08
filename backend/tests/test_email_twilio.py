import base64
import json
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge import providers
from routebridge.config.settings import Settings, get_settings
from routebridge.config.validation import production_problems
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.plans import NotificationDelivery
from routebridge.models.workflows import Notification
from routebridge.providers import LogMessagingProvider, ResendEmailProvider, TwilioMessagingProvider, normalize_phone
from routebridge.services import notifications
from routebridge.services.email_templates import render_email_html, subject_for

client = TestClient(app)
create_db_and_tables()


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- phone numbers
@pytest.mark.parametrize("given,expected", [
    ("08012345678", "+2348012345678"), ("0801 234 5678", "+2348012345678"), ("(0801) 234-5678", "+2348012345678"), ("2348012345678", "+2348012345678"),
    ("+234 801 234 5678", "+2348012345678"), ("8012345678", "+2348012345678"), ("00234 801 234 5678", "+2348012345678"), ("+14155550123", "+14155550123"), ("", ""),
])
def test_phone_numbers_are_made_international(given: str, expected: str) -> None:
    assert normalize_phone(given) == expected


# ---------------------------------------------------------------- Twilio
def test_a_twilio_text_has_the_right_address_login_and_fields() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], form={k: v[0] for k, v in parse_qs(request.content.decode()).items()})
        return httpx.Response(201, json={"sid": "SM999", "status": "queued"})

    provider = TwilioMessagingProvider("ACabc", "secret-token", "+15005550006", client=mock_client(handler))
    assert provider.send("08031234567", "Your parcel is on the way") == "SM999"
    assert seen["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACabc/Messages.json"
    assert base64.b64decode(seen["auth"].split(" ", 1)[1]).decode() == "ACabc:secret-token"
    assert seen["form"] == {"To": "+2348031234567", "From": "+15005550006", "Body": "Your parcel is on the way"}  # the local number was made international


def test_a_messaging_service_replaces_the_from_number() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["form"] = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        return httpx.Response(201, json={"sid": "SM1"})

    TwilioMessagingProvider("ACabc", "t", "", messaging_service_sid="MG123", client=mock_client(handler)).send("+2348031234567", "hi")
    assert seen["form"] == {"To": "+2348031234567", "MessagingServiceSid": "MG123", "Body": "hi"}


def test_a_twilio_refusal_says_why() -> None:
    handler = lambda request: httpx.Response(400, json={"code": 21608, "message": "The number +2348031234567 is unverified (trial account)", "status": 400})  # noqa: E731
    with pytest.raises(httpx.HTTPStatusError) as caught:
        TwilioMessagingProvider("ACabc", "t", "+15005550006", client=mock_client(handler)).send("+2348031234567", "hi")
    assert "21608" in str(caught.value) and "unverified" in str(caught.value)


def test_the_right_sms_provider_is_chosen(monkeypatch) -> None:
    settings = get_settings()
    saved = (settings.sms_provider, settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number, settings.twilio_messaging_service_sid, settings.sms_sender_id)
    try:
        settings.sms_provider, settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number, settings.twilio_messaging_service_sid, settings.sms_sender_id = "twilio", "ACx", "tok", "+15005550006", "", ""
        assert isinstance(providers.get_messaging_provider("sms"), TwilioMessagingProvider)
        settings.twilio_auth_token = ""
        assert providers.get_messaging_provider("sms") is None  # half-configured: nothing is pretended
        settings.sms_provider = "log"
        assert isinstance(providers.get_messaging_provider("sms"), LogMessagingProvider)  # explicit "log" is respected even with keys present
    finally:
        (settings.sms_provider, settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number, settings.twilio_messaging_service_sid, settings.sms_sender_id) = saved


def test_plain_environment_names_are_read(monkeypatch) -> None:
    for name, value in {"TWILIO_ACCOUNT_SID": "ACfromenv", "TWILIO_AUTH_TOKEN": "tok", "TWILIO_PHONE_NUMBER": "+15005550006", "RESEND_API_KEY": "re_key", "EMAIL_FROM": "RB <a@b.test>"}.items():
        monkeypatch.setenv(name, value)
    s = Settings(_env_file=None)
    assert (s.twilio_account_sid, s.twilio_phone_number, s.resend_api_key, s.email_from) == ("ACfromenv", "+15005550006", "re_key", "RB <a@b.test>")
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.setenv("ROUTEBRIDGE_RESEND_API_KEY", "re_prefixed")
    assert Settings(_env_file=None).resend_api_key == "re_prefixed"  # the prefixed name works as well


# ---------------------------------------------------------------- Resend
def test_a_resend_email_has_the_right_request() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content))
        return httpx.Response(200, json={"id": "em_123"})

    provider = ResendEmailProvider("re_secret", "RouteBridge Logistics <alerts@shop.test>", reply_to="help@shop.test", client=mock_client(handler))
    assert provider.send("owner@shop.test", "New order MP-1\n\nTrack it: https://app.test/track/abc", subject="New order received") == "em_123"
    assert seen["url"] == "https://api.resend.com/emails" and seen["auth"] == "Bearer re_secret"
    body = seen["body"]
    assert body["from"] == "RouteBridge Logistics <alerts@shop.test>" and body["to"] == ["owner@shop.test"] and body["reply_to"] == "help@shop.test"
    assert body["subject"] == "New order received" and "MP-1" in body["text"] and "<html" in body["html"]


def test_a_resend_refusal_says_why() -> None:
    handler = lambda request: httpx.Response(403, json={"name": "validation_error", "message": "You can only send testing emails to your own email address"})  # noqa: E731
    with pytest.raises(httpx.HTTPStatusError) as caught:
        ResendEmailProvider("re_x", "", client=mock_client(handler)).send("someone@else.test", "hi")
    assert "only send testing emails to your own email address" in str(caught.value)


def test_the_email_page_escapes_what_people_typed_and_links_urls() -> None:
    page = render_email_html("Order <b>1</b>", "Customer <script>alert(1)</script> & co\nSee https://app.test/track/abc.")
    assert "<script>" not in page and "&lt;script&gt;" in page and "Order &lt;b&gt;1&lt;/b&gt;" in page
    assert '<a href="https://app.test/track/abc"' in page and subject_for("merchant_welcome") == "Welcome to RouteBridge Logistics" and subject_for("nope").startswith("An update")


def test_the_provider_is_log_only_without_a_key() -> None:
    settings = get_settings()
    old = (settings.resend_api_key, settings.email_provider)
    try:
        settings.resend_api_key, settings.email_provider = "", "auto"
        assert isinstance(providers.get_email_provider(), providers.LogEmailProvider)
        settings.resend_api_key = "re_x"
        assert isinstance(providers.get_email_provider(), ResendEmailProvider)
        settings.email_provider = "log"
        assert isinstance(providers.get_email_provider(), providers.LogEmailProvider)
    finally:
        settings.resend_api_key, settings.email_provider = old


# ---------------------------------------------------------------- the email channel through the real queue
@pytest.fixture
def company():
    with Session(engine) as session:
        tenant = Tenant(name="Mail Logistics")
        session.add(tenant)
        session.commit()
        return str(tenant.id)


class Capture:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    def send(self, recipient, body, subject=None):
        self.sent.append((recipient, subject, body))
        return "em_test"


def rows(tenant_id: str, channel: str) -> list[Notification]:
    with Session(engine) as session:
        return list(session.exec(select(Notification).where(Notification.tenant_id == UUID(tenant_id), Notification.channel == channel)).all())


def test_a_shop_with_an_email_is_emailed_and_texted(company, monkeypatch) -> None:
    phone, mail = f"+23481{uuid4().int % 10**8:08d}", f"shop{uuid4().hex[:6]}@example.test"
    shop = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"name": "Mail Shop", "contact_phone": phone, "contact_email": mail.upper()})
    assert shop.status_code == 201 and shop.json()["contact_email"] == mail  # tidied to lower case
    client.post(f"/api/v1/tenants/{company}/orders", json={"merchant_id": shop.json()["id"], "customer_name": "Ada", "customer_phone": "08011112222", "external_ref": "ML-1", "address_text": "5 Bode Thomas"})
    assert {n.template for n in rows(company, "sms") if n.recipient == phone} == {"merchant_welcome", "merchant_order_created"}
    emails = [n for n in rows(company, "email") if n.recipient == mail]
    assert {n.template for n in emails} == {"merchant_welcome", "merchant_order_created"}

    fake = Capture()
    monkeypatch.setattr(notifications, "get_email_provider", lambda: fake)
    with Session(engine) as session:
        counts = notifications.dispatch_pending(session, tenant_id=UUID(company))
    assert counts["failed"] == 0 and sorted(s for _, s, _ in fake.sent) == ["New order received", "Welcome to RouteBridge Logistics"]
    assert all(recipient == mail for recipient, _, _ in fake.sent) and any("ML-1" in body for _, _, body in fake.sent)
    with Session(engine) as session:
        sent = session.exec(select(Notification).where(Notification.tenant_id == UUID(company), Notification.channel == "email")).all()
        assert sent and all(n.status == "sent" and n.provider_message_id == "em_test" for n in sent)
        assert all(session.exec(select(NotificationDelivery).where(NotificationDelivery.notification_id == n.id)).one().body == "[sent]" for n in sent)  # no content kept after sending


def test_a_bad_email_is_refused_and_switching_alerts_off_stops_both(company) -> None:
    assert client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"name": "Bad Mail", "contact_email": "not-an-email"}).status_code == 422
    mail = f"quiet{uuid4().hex[:6]}@example.test"
    shop = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"name": "Quiet Shop", "contact_email": mail}).json()
    client.patch(f"/api/v1/admin/tenants/{company}/merchants/{shop['id']}", json={"notify_orders": False})
    client.post(f"/api/v1/tenants/{company}/orders", json={"merchant_id": shop["id"], "customer_name": "Ada", "customer_phone": "08011112223", "external_ref": "QU-1", "address_text": "x"})
    assert [n.template for n in rows(company, "email") if n.recipient == mail] == ["merchant_welcome"]  # only the welcome, sent before the switch


def test_a_claim_decision_is_told_to_the_shop(company) -> None:
    mail = f"claims{uuid4().hex[:6]}@example.test"
    shop = client.post(f"/api/v1/admin/tenants/{company}/merchants", json={"name": "Claim Shop", "contact_email": mail}).json()
    claim = client.post(f"/api/v1/tenants/{company}/claims", json={"merchant_id": shop["id"], "kind": "damage", "description": "Box crushed on arrival", "amount_claimed": "5000"}).json()
    done = client.patch(f"/api/v1/tenants/{company}/claims/{claim['id']}", json={"status": "approved", "amount_approved": "4000", "resolution_note": "Photo checked."})
    assert done.status_code == 200, done.text
    with Session(engine) as session:
        mine = [n for n in session.exec(select(Notification).where(Notification.tenant_id == UUID(company), Notification.template == "claim_update")).all() if n.recipient == mail]
        body = session.exec(select(NotificationDelivery).where(NotificationDelivery.notification_id == mine[0].id)).one().body
    assert len(mine) == 1 and "approved for NGN 4,000" in body and "Photo checked." in body


# ---------------------------------------------------------------- production checks
def _prod(**over) -> Settings:
    base = dict(environment="production", database_url="postgresql+psycopg://u:p@db/rb", require_clerk_auth=True, clerk_webhook_secret="whsec_dGVzdA==", clerk_jwks_url="https://c.test/jwks",
                clerk_issuer="https://c.test", redis_url="redis://r:6379/0", verify_webhook_signatures=True, webhook_signing_secret="w" * 32, internal_api_key="i" * 24, driver_token_secret="d" * 32,
                allowed_origins=["https://app.example.test"], media_provider="s3", s3_endpoint="https://s3.test", s3_bucket="b", s3_access_key="a", s3_secret_key="s",
                public_tracking_base_url="https://app.example.test/track", sms_provider="twilio", twilio_account_sid="ACx", twilio_auth_token="t", twilio_phone_number="+15005550006")
    return Settings(**{**base, **over}, _env_file=None)


def test_production_accepts_a_complete_twilio_and_a_verified_sender() -> None:
    assert production_problems(_prod()) == []
    assert production_problems(_prod(resend_api_key="re_x", email_from="RouteBridge Logistics <alerts@shop.test>")) == []


def test_production_refuses_half_configured_messaging() -> None:
    assert any("TWILIO_ACCOUNT_SID" in p for p in production_problems(_prod(twilio_auth_token="")))
    assert any("test sender" in p for p in production_problems(_prod(resend_api_key="re_x")))  # a key with no verified sender
    assert any("test sender" in p for p in production_problems(_prod(resend_api_key="re_x", email_from="RB <onboarding@resend.dev>")))
    assert any("RESEND_API_KEY" in p for p in production_problems(_prod(email_provider="resend")))
