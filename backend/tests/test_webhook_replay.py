"""Idempotency proved through the replay harness: duplicates, out-of-order delivery, retries and true concurrency.

Each test ends by asserting on the DATABASE (rows, plan dates, audit events), not only on HTTP answers.
"""
import base64
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.billing import BillingPayment
from routebridge.models.core import Tenant
from routebridge.models.events import OutboxEvent
from routebridge.models.webhooks import WebhookReceipt
from webhook_harness import Replayer, paystack, svix

client = TestClient(app)
create_db_and_tables()
SECRET = "sk_test_replay_secret"
CLERK_SECRET = "whsec_" + base64.b64encode(b"replay-harness-clerk-secret-0123456789").decode()
PRICE = 75_000 * 100


@pytest.fixture(autouse=True)
def secrets():
    settings = get_settings()
    old = (settings.paystack_secret_key, settings.clerk_webhook_secret)
    settings.paystack_secret_key, settings.clerk_webhook_secret = SECRET, CLERK_SECRET
    yield
    settings.paystack_secret_key, settings.clerk_webhook_secret = old


def new_payment() -> tuple[UUID, str]:
    reference = f"rb_{uuid4().hex[:12]}"
    with Session(engine) as session:
        tenant = Tenant(name="Replay Logistics", plan="starter")
        session.add(tenant)
        session.commit()
        session.add(BillingPayment(tenant_id=tenant.id, reference=reference, plan="growth", amount_kobo=PRICE, payer_email="a@b.test"))
        session.commit()
        return tenant.id, reference


def charge(reference: str, amount: int = PRICE, status: str = "success") -> dict:
    return {"event": "charge.success", "data": {"reference": reference, "amount": amount, "status": status}}


def outcome(tenant_id: UUID, reference: str) -> dict:
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        payment = session.exec(select(BillingPayment).where(BillingPayment.reference == reference)).one()
        paid_events = session.exec(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_type == "billing.paid")).one()
        return {"plan": tenant.plan, "valid_until": tenant.plan_valid_until, "status": payment.status, "paid_events": paid_events}


@pytest.mark.parametrize("seed", range(12))
def test_duplicates_and_noise_in_any_order_buy_the_plan_exactly_once(seed: int) -> None:
    tenant_id, reference = new_payment()
    replay = Replayer(client)
    good = paystack("good", charge(reference), SECRET)
    noise = [
        paystack("forged", charge(reference), SECRET, valid=False),               # wrong signature
        paystack("short", charge(reference, amount=100), SECRET),                 # wrong amount
        paystack("declined", charge(reference, status="failed"), SECRET),         # failed charge
        paystack("stranger", charge("rb_does_not_exist"), SECRET),                # unknown reference
    ]
    replay.shuffled([good, good, good, *noise, *noise], seed)
    # a final clean delivery settles whatever order the noise arrived in
    replay.send(good)
    result = outcome(tenant_id, reference)
    assert result["status"] == "success", replay.dump()
    assert result["plan"] == "growth" and result["valid_until"] is not None
    assert result["paid_events"] == 1, replay.dump()  # one audit event however many deliveries
    assert set(replay.statuses("forged")) == {401}
    assert replay.statuses("stranger") and set(replay.statuses("stranger")) == {200}  # unknown reference is acknowledged, changes nothing


def test_a_later_retry_never_extends_the_plan_again() -> None:
    tenant_id, reference = new_payment()
    replay = Replayer(client)
    good = paystack("good", charge(reference), SECRET)
    replay.send(good)
    first = outcome(tenant_id, reference)
    replay.duplicated([good], 5)
    assert outcome(tenant_id, reference) == first


def test_a_failed_attempt_arriving_first_does_not_block_the_real_payment() -> None:
    tenant_id, reference = new_payment()
    replay = Replayer(client)
    replay.in_order([paystack("short", charge(reference, amount=100), SECRET)])
    assert outcome(tenant_id, reference)["status"] == "failed"
    replay.in_order([paystack("good", charge(reference), SECRET)])
    result = outcome(tenant_id, reference)
    assert result["status"] == "success" and result["plan"] == "growth" and result["paid_events"] == 1


def test_a_failed_report_after_success_does_not_undo_it() -> None:
    tenant_id, reference = new_payment()
    replay = Replayer(client)
    replay.in_order([paystack("good", charge(reference), SECRET), paystack("declined", charge(reference, status="failed"), SECRET)])
    assert outcome(tenant_id, reference)["status"] == "success"


def test_the_same_webhook_event_sent_at_the_same_moment_is_processed_once() -> None:
    event_id = f"evt_{uuid4().hex}"
    body = {"id": event_id, "type": "ping"}
    replay = Replayer(client)
    from webhook_harness import Delivery
    import hashlib
    import hmac
    import json
    settings = get_settings()
    old = (settings.verify_webhook_signatures, settings.webhook_signing_secret)
    settings.verify_webhook_signatures, settings.webhook_signing_secret = True, "replay-signing-secret"
    try:
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.HMAC(b"replay-signing-secret", canonical, hashlib.sha256).hexdigest()
        delivery = Delivery("same", "/api/v1/webhooks/acme", json.dumps(body).encode(), {"x-webhook-signature": signature, "content-type": "application/json"})
        answers = replay.at_once([delivery] * 8)
    finally:
        settings.verify_webhook_signatures, settings.webhook_signing_secret = old
    assert sorted(a.status for a in answers) == [200] * 8, replay.dump()
    assert sorted(a.json["status"] for a in answers) == ["accepted"] + ["duplicate"] * 7, replay.dump()
    with Session(engine) as session:
        assert session.exec(select(func.count()).select_from(WebhookReceipt).where(WebhookReceipt.event_id == event_id)).one() == 1


def test_clerk_events_replayed_and_shuffled_create_one_user() -> None:
    from routebridge.models.access import User
    user_id = f"user_{uuid4().hex[:12]}"
    created = {"type": "user.created", "data": {"id": user_id, "first_name": "Ada", "last_name": "Okafor", "email_addresses": [{"email_address": f"{user_id}@example.test"}]}}
    updated = {"type": "user.updated", "data": {"id": user_id, "first_name": "Ada", "last_name": "Eze", "email_addresses": [{"email_address": f"{user_id}@example.test"}]}}
    replay = Replayer(client)
    deliveries = [svix("created", created, CLERK_SECRET, f"msg_{uuid4().hex}"), svix("updated", updated, CLERK_SECRET, f"msg_{uuid4().hex}")]
    replay.shuffled(deliveries, seed=3)            # updated may arrive before created
    replay.duplicated(deliveries, 3)               # then retries of both
    assert set(replay.statuses()) == {200}, replay.dump()
    with Session(engine) as session:
        assert len(session.exec(select(User).where(User.clerk_user_id == user_id)).all()) == 1  # never two accounts
