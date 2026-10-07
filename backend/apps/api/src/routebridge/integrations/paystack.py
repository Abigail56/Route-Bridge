"""Paystack (cards and bank transfer in naira). Two calls: start a payment, and ask whether a payment really succeeded."""
import hashlib
import hmac

import httpx

from routebridge.config.settings import get_settings

API = "https://api.paystack.co"


class PaystackError(Exception):
    pass


class PaystackClient:
    def __init__(self, secret_key: str, client: httpx.Client | None = None) -> None:
        self.secret_key = secret_key
        self.client = client or httpx.Client(timeout=15.0)

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self.client.request(method, API + path, headers={"Authorization": f"Bearer {self.secret_key}"}, **kwargs)
            body = response.json() if response.content else {}
        except httpx.HTTPError as exc:
            raise PaystackError("Could not reach Paystack. Try again in a moment.") from exc
        if response.status_code >= 400 or not body.get("status"):
            raise PaystackError(body.get("message") or "Paystack refused the request.")
        return body.get("data") or {}

    def initialize(self, *, email: str, amount_kobo: int, reference: str, callback_url: str, metadata: dict) -> dict:
        return self._call("POST", "/transaction/initialize", json={"email": email, "amount": amount_kobo, "currency": "NGN", "reference": reference, "callback_url": callback_url, "metadata": metadata})

    def verify(self, reference: str) -> dict:
        return self._call("GET", f"/transaction/verify/{reference}")


def webhook_signature_ok(secret_key: str, body: bytes, signature: str | None) -> bool:
    """Paystack signs every webhook with HMAC-SHA512 of the raw body, using your secret key."""
    if not secret_key or not signature:
        return False
    expected = hmac.new(secret_key.encode("utf-8"), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def get_paystack() -> PaystackClient | None:
    key = get_settings().paystack_secret_key
    return PaystackClient(key) if key else None
