"""Verify Svix-signed webhooks (Clerk delivers its webhooks through Svix).

Signed content is `{svix-id}.{svix-timestamp}.{raw body}`, HMAC-SHA256 with the base64-decoded secret (the part after
`whsec_`), base64-encoded, and sent as `v1,<signature>` (several space-separated signatures during secret rotation).
"""
import base64
import binascii
import hashlib
import hmac
import time

from fastapi import HTTPException

TOLERANCE_SECONDS = 300


def verify_svix(secret: str, msg_id: str | None, timestamp: str | None, signature_header: str | None, body: bytes, tolerance: int = TOLERANCE_SECONDS) -> None:
    """Raise 401 unless the request carries a valid, fresh Svix signature."""
    invalid = HTTPException(status_code=401, detail="Invalid webhook signature")
    if not (msg_id and timestamp and signature_header):
        raise invalid
    try:
        sent_at = int(timestamp)
    except ValueError:
        raise invalid from None
    if abs(time.time() - sent_at) > tolerance:
        raise HTTPException(status_code=401, detail="Webhook timestamp outside the allowed window")
    try:
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    except (binascii.Error, IndexError):
        raise HTTPException(status_code=503, detail="Clerk webhook secret is misconfigured") from None
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    candidates = [part.split(",", 1)[1] for part in signature_header.split() if part.startswith("v1,")]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise invalid
