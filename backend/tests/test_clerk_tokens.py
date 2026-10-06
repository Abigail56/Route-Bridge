import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from routebridge.config.settings import get_settings
from routebridge.integrations import clerk

ISSUER = "https://example.clerk.accounts.dev"


@pytest.fixture
def signer(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = get_settings()
    monkeypatch.setattr(settings, "clerk_jwks_url", "https://example.clerk.accounts.dev/.well-known/jwks.json")
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)

    class FakeClient:
        def get_signing_key_from_jwt(self, _token):
            return type("Key", (), {"key": key.public_key()})()

    monkeypatch.setattr(clerk, "_jwks_client", lambda: FakeClient())

    def make(offset_seconds: int) -> str:
        now = int(time.time())
        return jwt.encode({"sub": "user_abc", "iss": ISSUER, "iat": now - 600, "nbf": now - 600, "exp": now + offset_seconds}, key, algorithm="RS256")

    return make


def test_a_token_a_little_past_its_expiry_is_still_accepted(signer) -> None:
    # 30 seconds of clock drift between this server and Clerk must not sign anyone out
    assert clerk.verify_clerk_token(signer(-30)).subject == "user_abc"


def test_a_really_expired_token_says_so(signer) -> None:
    with pytest.raises(HTTPException) as caught:
        clerk.verify_clerk_token(signer(-300))
    assert caught.value.status_code == 401 and "expired" in caught.value.detail.lower()


def test_failing_to_reach_clerk_is_not_reported_as_an_expired_session(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "clerk_jwks_url", "https://example.clerk.accounts.dev/.well-known/jwks.json")

    class Unreachable:
        def get_signing_key_from_jwt(self, _token):
            raise jwt.PyJWKClientConnectionError("network down")

    monkeypatch.setattr(clerk, "_jwks_client", lambda: Unreachable())
    with pytest.raises(HTTPException) as caught:
        clerk.verify_clerk_token("a.b.c")
    assert caught.value.status_code == 503
