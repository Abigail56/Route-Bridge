from fastapi.testclient import TestClient
from uuid import uuid4

from routebridge.main import app


def test_signup_is_limited_to_five_attempts_per_ip_and_identifier() -> None:
    with TestClient(app) as client:
        identifier = "signup-limit@example.test"
        responses = [client.post("/api/v1/auth/signup", json={"identifier": identifier}) for _ in range(6)]
        assert [response.status_code for response in responses[:5]] == [200] * 5
        assert responses[5].status_code == 429
        assert responses[5].headers["retry-after"]


def test_signin_has_a_separate_five_attempt_window() -> None:
    with TestClient(app) as client:
        identifier = "signin-limit@example.test"
        responses = [client.post("/api/v1/auth/signin", json={"identifier": identifier}) for _ in range(6)]
        assert [response.status_code for response in responses[:5]] == [200] * 5
        assert responses[5].status_code == 429


def test_webhook_event_is_processed_once_and_replays_are_duplicates() -> None:
    with TestClient(app) as client:
        headers = {"X-Webhook-Event-ID": f"clerk_evt_{uuid4()}"}
        payload = {"type": "user.created", "data": {"id": "user_001"}}
        first = client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
        duplicate = client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
        assert first.status_code == 200
        assert first.json()["duplicate"] is False
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "duplicate"
        assert duplicate.json()["duplicate"] is True


def test_webhook_reused_event_id_with_changed_payload_is_rejected() -> None:
    with TestClient(app) as client:
        headers = {"X-Webhook-Event-ID": f"clerk_evt_{uuid4()}"}
        first = client.post("/api/v1/webhooks/clerk", json={"type": "user.created", "data": {"id": f"user_{uuid4()}"}}, headers=headers)
        changed = client.post("/api/v1/webhooks/clerk", json={"type": "user.deleted", "data": {"id": f"user_{uuid4()}"}}, headers=headers)
        assert first.status_code == 200
        assert changed.status_code == 409
