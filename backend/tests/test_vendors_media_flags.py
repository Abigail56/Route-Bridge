import datetime as dt
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import Settings, get_settings
from routebridge.config.validation import production_problems, validate_production_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.integrations.circuit import CircuitBreaker, CircuitOpenError
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.orders import Merchant
from routebridge.models.workflows import Notification
from routebridge.providers import HttpMessagingProvider, HttpTelephonyProvider, NominatimGeocoder
from routebridge.services import storage
from routebridge.services.flags import enabled, snapshot

client = TestClient(app)
create_db_and_tables()


def _mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---- vendor adapter contracts (mocked transport: request shape, auth placement, failure handling) -------------------


def test_default_sms_body_and_bearer_auth() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(headers=dict(request.headers), body=json.loads(request.content))
        return httpx.Response(200, json={"id": "msg-1"})

    provider = HttpMessagingProvider("https://gw.test/send", "KEY", "RouteBridge", "sms", CircuitBreaker(), _mock(handler))
    assert provider.send("+2348012345678", "hello") == "msg-1"
    assert seen["headers"]["authorization"] == "Bearer KEY"
    assert seen["body"] == {"to": "+2348012345678", "from": "RouteBridge", "channel": "sms", "message": "hello"}


def test_vendor_template_with_api_key_in_body_and_custom_header() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append((dict(request.headers), json.loads(request.content)))
        return httpx.Response(200, json={"messageId": "abc"})

    template = '{"to": "{to}", "from": "{from}", "sms": "{message}", "type": "plain", "channel": "generic"}'
    body_auth = HttpMessagingProvider("https://gw.test", "SECRET", "RB", "sms", CircuitBreaker(), _mock(handler), template, "body:api_key")
    assert body_auth.send("0801", "hi") == "abc"
    header_auth = HttpMessagingProvider("https://gw.test", "SECRET", "RB", "sms", CircuitBreaker(), _mock(handler), template, "header:X-Api-Key")
    header_auth.send("0801", "hi")
    assert bodies[0][1] == {"to": "0801", "from": "RB", "sms": "hi", "type": "plain", "channel": "generic", "api_key": "SECRET"}
    assert "authorization" not in bodies[0][0]
    assert bodies[1][0]["x-api-key"] == "SECRET" and "api_key" not in bodies[1][1]
    with pytest.raises(ValueError):
        HttpMessagingProvider("https://gw.test", "K", "RB", "sms", CircuitBreaker(), _mock(handler), "", "nonsense").send("1", "x")


def test_circuit_breaker_stops_hammering_a_failing_gateway() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    provider = HttpMessagingProvider("https://gw.test", "K", "RB", "sms", CircuitBreaker(failure_threshold=3, reset_seconds=60), _mock(handler))
    for _ in range(3):
        with pytest.raises(httpx.HTTPStatusError):
            provider.send("0801", "x")
    with pytest.raises(CircuitOpenError):
        provider.send("0801", "x")
    assert len(calls) == 3  # the fourth attempt never reached the gateway


def test_geocoder_parses_caches_and_degrades_gracefully() -> None:
    calls = []

    def ok(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=[{"lat": "6.6018", "lon": "3.3515", "place_id": 42}])

    geocoder = NominatimGeocoder("https://geo.test/search", CircuitBreaker(), _mock(ok))
    first = geocoder.geocode("12 Allen Ave, Ikeja", "Opposite the blue gate")
    assert (first.latitude, first.longitude, first.confidence) == (6.6018, 3.3515, "geocoded")
    geocoder.geocode("12 Allen Ave, Ikeja", "Opposite the blue gate")
    assert len(calls) == 1 and calls[0]["countrycodes"] == "ng"  # second call served from cache
    broken = NominatimGeocoder("https://geo.test/search", CircuitBreaker(), _mock(lambda r: httpx.Response(500)))
    assert broken.geocode("anywhere") is None  # failure -> caller falls back to manual coordinates / plus code
    empty = NominatimGeocoder("https://geo.test/search", CircuitBreaker(), _mock(lambda r: httpx.Response(200, json=[])))
    assert empty.geocode("nowhere") is None


def test_telephony_bridge_request_shape() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(body=json.loads(request.content), auth=request.headers["authorization"])
        return httpx.Response(200, json={"session_id": "call-9"})

    provider = HttpTelephonyProvider("https://tel.test/bridge", "TK", CircuitBreaker(), _mock(handler))
    assert provider.bridge_call("0801", "0802", "RB-1") == "call-9"
    assert seen["body"] == {"party_a": "0801", "party_b": "0802", "reference": "RB-1"} and seen["auth"] == "Bearer TK"


# ---- object storage ----------------------------------------------------------------------------------------------


def test_presigned_url_matches_the_aws_documented_example() -> None:
    url = storage.presign_url(
        "GET", "https://s3.amazonaws.com", "examplebucket", "test.txt", "us-east-1", "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", 86400, now=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc), virtual_host=True,
    )
    assert url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404")


def test_local_storage_rejects_path_traversal_and_bad_types() -> None:
    assert not storage.valid_key("../etc/passwd") and not storage.valid_key("a/../../b.jpg")
    with pytest.raises(ValueError):
        storage.new_object_key(uuid4(), uuid4(), "photo", "application/pdf")
    with pytest.raises(ValueError):
        storage.new_object_key(uuid4(), uuid4(), "selfie", "image/jpeg")


# ---- production configuration ------------------------------------------------------------------------------------


def _prod(**overrides) -> Settings:
    base = dict(
        environment="production", database_url="postgresql+psycopg://u:p@db/rb", require_clerk_auth=True, clerk_webhook_secret="whsec_dGVzdC1zZWNyZXQ=", clerk_jwks_url="https://clerk.test/jwks", clerk_issuer="https://clerk.test",
        redis_url="redis://r:6379/0", verify_webhook_signatures=True, webhook_signing_secret="w" * 32, internal_api_key="i" * 24, driver_token_secret="d" * 32,
        allowed_origins=["https://app.routebridge.ng"], sms_provider="http", sms_api_url="https://gw.test", sms_api_key="k", media_provider="s3",
        s3_endpoint="https://s3.test", s3_bucket="b", s3_access_key="a", s3_secret_key="s", public_tracking_base_url="https://track.routebridge.ng",
    )
    return Settings(**{**base, **overrides}, _env_file=None)


def test_production_validation_accepts_a_complete_configuration_and_names_every_gap() -> None:
    assert production_problems(_prod()) == []
    validate_production_settings(_prod())
    allowed = _prod(sms_provider="log", allow_log_sms=True)
    assert not [p for p in production_problems(allowed) if "SMS" in p]  # a knowing opt-out is accepted
    assert [p for p in production_problems(_prod(sms_provider="log")) if "SMS" in p]  # but never by accident
    bad = _prod(clerk_webhook_secret="", sms_provider="log", driver_token_secret="", webhook_signing_secret="short", allowed_origins=["http://localhost:3000"], redis_url="", media_provider="local", database_url="sqlite:///x.db")
    problems = "\n".join(production_problems(bad))
    for needle in ("CLERK_WEBHOOK_SECRET", "SMS is not configured", "DRIVER_TOKEN_SECRET", "WEBHOOK_SIGNING_SECRET", "non-production origin", "REDIS_URL", "MEDIA_PROVIDER=local", "must be PostgreSQL"):
        assert needle in problems
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        validate_production_settings(bad)
    assert production_problems(Settings(environment="development", _env_file=None)) == []  # dev stays permissive


# ---- feature flags ----------------------------------------------------------------------------------------------


def test_feature_flags_default_and_override() -> None:
    settings = get_settings()
    assert enabled("masked_calls") and not enabled("unknown_flag")
    settings.feature_flags["masked_calls"] = False
    try:
        assert not enabled("masked_calls") and snapshot()["masked_calls"] is False
    finally:
        settings.feature_flags.pop("masked_calls")


# ---- driver call / message / uploads end to end ------------------------------------------------------------------


@pytest.fixture
def configured(tmp_path):
    settings = get_settings()
    old = (settings.driver_token_secret, settings.media_dir, settings.media_provider)
    settings.driver_token_secret, settings.media_dir, settings.media_provider = "d" * 32, str(tmp_path), "local"
    yield
    settings.driver_token_secret, settings.media_dir, settings.media_provider = old
    settings.feature_flags.clear()


def _active_job():
    with Session(engine) as session:
        tenant = Tenant(name="Driver Extras")
        session.add(tenant)
        session.flush()
        merchant = Merchant(tenant_id=tenant.id, name="Extras Merchant")
        session.add(merchant)
        session.commit()
        tenant_id, merchant_id = tenant.id, merchant.id
    order = client.post(f"/api/v1/tenants/{tenant_id}/orders", json={"merchant_id": str(merchant_id), "customer_name": "Ada", "customer_phone": "+2348055551234", "external_ref": "X-1", "address_text": "Yaba"}).json()
    driver = client.post(f"/api/v1/tenants/{tenant_id}/drivers", json={"name": "Chisom Obi", "phone": "08066661234"}).json()
    job = order["delivery_job_id"]
    client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/assignments", json={"driver_id": driver["id"]})
    token = client.post(f"/api/v1/tenants/{tenant_id}/drivers/{driver['id']}/token").json()["access_token"]
    return tenant_id, job, {"Authorization": f"Bearer {token}"}


def test_masked_call_and_message_never_expose_numbers(configured) -> None:
    tenant_id, job, auth = _active_job()
    call = client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/call", headers=auth)
    assert call.status_code == 200 and call.json()["status"] == "connecting" and "2348055551234" not in call.text
    sent = client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/message", json={"text": "I am at the gate"}, headers=auth)
    assert sent.status_code == 201
    with Session(engine) as session:
        queued = session.exec(select(Notification).where(Notification.tenant_id == tenant_id, Notification.template == "driver_message")).all()
        assert len(queued) == 1
    assert client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/message", json={"text": ""}, headers=auth).status_code == 422
    assert client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{uuid4()}/call", headers=auth).status_code == 404
    assert client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/call").status_code == 401
    get_settings().feature_flags["masked_calls"] = False
    assert client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/call", headers=auth).status_code == 404


def test_photo_upload_proof_and_staff_access(configured) -> None:
    tenant_id, job, auth = _active_job()
    for target in ("accepted", "en_route", "arrived"):
        client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/transitions", json={"target_status": target})
    grant = client.post(f"/api/v1/driver/tenants/{tenant_id}/jobs/{job}/uploads", json={"kind": "photo", "content_type": "image/jpeg"}, headers=auth).json()
    assert grant["object_url"].startswith(f"media://{tenant_id}/{job}/photo-") and grant["needs_auth"] is True
    path = grant["upload_url"].split("/api/v1", 1)[1]
    image = b"\xff\xd8\xff\xe0" + b"0" * 100
    assert client.put(f"/api/v1{path}", content=image, headers={**auth, "Content-Type": "image/jpeg"}).status_code == 201
    assert client.put(f"/api/v1{path}", content=image, headers={**auth, "Content-Type": "text/html"}).status_code == 415
    assert client.put(f"/api/v1{path}", content=b"", headers={**auth, "Content-Type": "image/jpeg"}).status_code == 413
    assert client.put(f"/api/v1{path}", content=image, headers={"Content-Type": "image/jpeg"}).status_code == 401
    other_tenant = uuid4()
    assert client.put(f"/api/v1/driver/tenants/{tenant_id}/media/{other_tenant}/{job}/photo-abcdef0123456789.jpg", content=image, headers={**auth, "Content-Type": "image/jpeg"}).status_code == 404

    # evidence from another delivery is rejected; this delivery's own photo is accepted and staff can view it
    foreign = client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/proof", json={"photo_url": f"media://{tenant_id}/{uuid4()}/photo-abcdef0123456789.jpg"})
    assert foreign.status_code == 422
    proof = client.post(f"/api/v1/tenants/{tenant_id}/delivery-jobs/{job}/proof", json={"photo_url": grant["object_url"], "recipient_name": "Ada"})
    assert proof.status_code == 201, proof.text
    key = grant["object_url"].removeprefix("media://")
    shown = client.get(f"/api/v1/tenants/{tenant_id}/media/{key}")
    assert shown.status_code == 200 and shown.content == image and shown.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/v1/tenants/{tenant_id}/media/{uuid4()}/{job}/x.jpg").status_code == 404
