import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from routebridge.config.settings import get_settings
from routebridge.db.session import create_db_and_tables, engine
from routebridge.main import app
from routebridge.models.access import User

client = TestClient(app)
create_db_and_tables()

SECRET = "whsec_" + base64.b64encode(b"clerk-webhook-test-secret-0123456789").decode()


def _signed(body: bytes, msg_id: str, timestamp: int | None = None, secret: str = SECRET) -> dict:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    key = base64.b64decode(secret.split("_", 1)[1])
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}", "content-type": "application/json"}


@pytest.fixture(autouse=True)
def clerk_secret():
    settings = get_settings()
    old = settings.clerk_webhook_secret
    settings.clerk_webhook_secret = SECRET
    yield
    settings.clerk_webhook_secret = old


def _event(user_id: str) -> bytes:
    return json.dumps({"type": "user.created", "data": {"id": user_id, "first_name": "Ada", "last_name": "Okafor", "email_addresses": [{"email_address": "ada@example.test"}]}}).encode()


def test_valid_svix_signature_syncs_the_user_and_replays_are_duplicates() -> None:
    user_id, msg_id = f"user_{uuid4().hex[:12]}", f"msg_{uuid4().hex}"
    body = _event(user_id)
    first = client.post("/api/v1/webhooks/clerk", content=body, headers=_signed(body, msg_id))
    assert first.status_code == 200 and first.json()["status"] == "accepted", first.text
    with Session(engine) as session:
        user = session.exec(select(User).where(User.clerk_user_id == user_id)).one()
        assert user.full_name == "Ada Okafor" and user.email == "ada@example.test"
    again = client.post("/api/v1/webhooks/clerk", content=body, headers=_signed(body, msg_id))
    assert again.status_code == 200 and again.json()["status"] == "duplicate"


def test_bad_stale_or_missing_signatures_are_rejected_and_nothing_is_stored() -> None:
    user_id = f"user_{uuid4().hex[:12]}"
    body = _event(user_id)
    msg_id = f"msg_{uuid4().hex}"
    wrong_secret = "whsec_" + base64.b64encode(b"some-other-secret-value-0123456789").decode()
    assert client.post("/api/v1/webhooks/clerk", content=body, headers=_signed(body, msg_id, secret=wrong_secret)).status_code == 401
    assert client.post("/api/v1/webhooks/clerk", content=body + b" ", headers=_signed(body, msg_id)).status_code == 401  # body changed after signing
    assert client.post("/api/v1/webhooks/clerk", content=body, headers=_signed(body, msg_id, timestamp=int(time.time()) - 3600)).status_code == 401
    assert client.post("/api/v1/webhooks/clerk", content=body, headers={"content-type": "application/json"}).status_code == 401
    # the previous custom scheme no longer works for Clerk once the Svix secret is configured
    assert client.post("/api/v1/webhooks/clerk", content=body, headers={"X-Webhook-Event-ID": msg_id, "content-type": "application/json"}).status_code == 401
    with Session(engine) as session:
        assert session.exec(select(User).where(User.clerk_user_id == user_id)).first() is None


def test_rotated_secret_accepts_either_signature() -> None:
    body, msg_id = _event(f"user_{uuid4().hex[:12]}"), f"msg_{uuid4().hex}"
    headers = _signed(body, msg_id)
    old = _signed(body, msg_id, secret="whsec_" + base64.b64encode(b"retired-secret-value-0123456789ab").decode())["svix-signature"]
    headers["svix-signature"] = f"{old} {headers['svix-signature']}"  # Svix sends both during rotation
    assert client.post("/api/v1/webhooks/clerk", content=body, headers=headers).status_code == 200
