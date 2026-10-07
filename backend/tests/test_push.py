from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.core import Tenant
from routebridge.models.events import OutboxEvent
from routebridge.models.orders import Merchant
from routebridge.models.push import PushSubscription
from routebridge.services import push
from routebridge.tools.gen_secrets import vapid_pair

client = TestClient(app)
create_db_and_tables()
PUBLIC, PRIVATE = vapid_pair()


@pytest.fixture(autouse=True)
def configured():
    settings = get_settings()
    old = (settings.driver_token_secret, settings.vapid_public_key, settings.vapid_private_key)
    settings.driver_token_secret = "d" * 32
    settings.vapid_public_key, settings.vapid_private_key = PUBLIC, PRIVATE
    yield
    settings.driver_token_secret, settings.vapid_public_key, settings.vapid_private_key = old


@pytest.fixture
def rider():
    with Session(engine) as session:
        tenant = Tenant(name="Push Logistics")
        session.add(tenant)
        session.flush()
        shop = Merchant(tenant_id=tenant.id, name="Shop")
        session.add(shop)
        session.commit()
        t, m = str(tenant.id), str(shop.id)
    driver = client.post(f"/api/v1/tenants/{t}/drivers", json={"name": "Push Rider", "phone": f"+23480{uuid4().int % 10**8:08d}"}).json()
    token = client.post(f"/api/v1/tenants/{t}/drivers/{driver['id']}/token").json()["access_token"]
    return {"tenant": t, "merchant": m, "driver": driver["id"], "headers": {"Authorization": f"Bearer {token}"}}


def sub_body(endpoint="https://push.example.test/abc"):
    return {"endpoint": endpoint, "keys": {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}}


def test_the_key_is_offered_only_when_alerts_are_set_up(rider) -> None:
    url = f"/api/v1/driver/tenants/{rider['tenant']}/push/key"
    assert client.get(url, headers=rider["headers"]).json()["public_key"] == PUBLIC
    get_settings().vapid_private_key = ""
    assert client.get(url, headers=rider["headers"]).json()["public_key"] is None
    assert client.get(url).status_code == 401


def test_subscribing_is_idempotent_and_a_phone_can_move_to_another_rider(rider) -> None:
    base = f"/api/v1/driver/tenants/{rider['tenant']}/push"
    assert client.post(f"{base}/subscribe", json=sub_body(), headers=rider["headers"]).status_code == 201
    assert client.post(f"{base}/subscribe", json=sub_body(), headers=rider["headers"]).status_code == 201
    with Session(engine) as session:
        assert len(session.exec(select(PushSubscription).where(PushSubscription.driver_id == UUID(rider["driver"]))).all()) == 1
    assert client.post(f"{base}/unsubscribe", json={"endpoint": sub_body()["endpoint"]}, headers=rider["headers"]).status_code == 200
    with Session(engine) as session:
        assert session.exec(select(PushSubscription).where(PushSubscription.driver_id == UUID(rider["driver"]))).first() is None


def test_a_bad_subscription_is_refused(rider) -> None:
    res = client.post(f"/api/v1/driver/tenants/{rider['tenant']}/push/subscribe", json={"endpoint": "x", "keys": {"p256dh": "a", "auth": "b"}}, headers=rider["headers"])
    assert res.status_code == 422


def test_an_assignment_event_pushes_to_the_riders_phones(rider, monkeypatch) -> None:
    client.post(f"/api/v1/driver/tenants/{rider['tenant']}/push/subscribe", json=sub_body(), headers=rider["headers"])
    sent = []
    monkeypatch.setattr(push, "_send", lambda sub, payload: sent.append((sub.endpoint, payload)) or None)
    order = client.post(f"/api/v1/tenants/{rider['tenant']}/orders", json={"merchant_id": rider["merchant"], "customer_name": "C", "customer_phone": "+2348011111111", "external_ref": "PUSH-1", "address_text": "12 Allen Avenue"}).json()
    with Session(engine) as session:
        event = OutboxEvent(tenant_id=UUID(rider["tenant"]), event_type="delivery.assignment.created", aggregate_type="delivery_job", aggregate_id=UUID(order["delivery_job_id"]), payload={"driver_id": rider["driver"]})
        session.add(event)
        session.flush()
        push.handle_event(session, event)
        session.commit()
    assert len(sent) == 1 and sent[0][1]["title"] == "New delivery assigned" and "PUSH-1" in sent[0][1]["body"] and "12 Allen Avenue" in sent[0][1]["body"]


def test_other_events_and_a_disabled_setup_push_nothing(rider, monkeypatch) -> None:
    client.post(f"/api/v1/driver/tenants/{rider['tenant']}/push/subscribe", json=sub_body(), headers=rider["headers"])
    sent = []
    monkeypatch.setattr(push, "_send", lambda sub, payload: sent.append(1) or None)
    with Session(engine) as session:
        other = OutboxEvent(tenant_id=UUID(rider["tenant"]), event_type="order.created", aggregate_type="order", aggregate_id=uuid4(), payload={})
        push.handle_event(session, other)
        get_settings().vapid_private_key = ""
        assign = OutboxEvent(tenant_id=UUID(rider["tenant"]), event_type="delivery.assignment.created", aggregate_type="delivery_job", aggregate_id=uuid4(), payload={"driver_id": rider["driver"]})
        push.handle_event(session, assign)
    assert sent == []


def test_dead_subscriptions_are_removed_and_flaky_ones_are_tried_again(rider, monkeypatch) -> None:
    base = f"/api/v1/driver/tenants/{rider['tenant']}/push/subscribe"
    client.post(base, json=sub_body("https://push.example.test/gone"), headers=rider["headers"])
    client.post(base, json=sub_body("https://push.example.test/flaky"), headers=rider["headers"])
    monkeypatch.setattr(push, "_send", lambda sub, payload: 410 if sub.endpoint.endswith("gone") else 500)
    with Session(engine) as session:
        assert push.notify_driver(session, UUID(rider["driver"]), "t", "b") == 0
        session.commit()
    with Session(engine) as session:
        left = session.exec(select(PushSubscription).where(PushSubscription.driver_id == UUID(rider["driver"]))).all()
        assert [s.endpoint for s in left] == ["https://push.example.test/flaky"] and left[0].failures == 1


def test_the_generated_keys_really_sign_a_push(rider, monkeypatch) -> None:
    """Runs the real pywebpush with the generated key pair; only the final HTTP call to the phone maker's server is replaced."""
    import requests

    seen = {}

    class Reply:
        status_code = 201
        text = ""
        headers = {}
        content = b""

    def fake_post(url, data=None, headers=None, **kwargs):
        seen["url"], seen["headers"] = url, headers
        return Reply()

    monkeypatch.setattr(requests, "post", fake_post)
    client.post(f"/api/v1/driver/tenants/{rider['tenant']}/push/subscribe", json=sub_body(), headers=rider["headers"])
    with Session(engine) as session:
        subscription = session.exec(select(PushSubscription).where(PushSubscription.driver_id == UUID(rider["driver"]))).one()
        assert push._send(subscription, {"title": "t", "body": "b"}) is None
    assert seen["url"] == "https://push.example.test/abc"
    assert seen["headers"]["Authorization"].startswith("vapid ") and seen["headers"]["Content-Encoding"] == "aes128gcm"
