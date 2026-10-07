"""Print strong values for the secrets the production configuration check requires.

    python -m routebridge.tools.gen_secrets > secrets.env      # then load into your secret manager; never commit it
"""
import base64
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid_pair() -> tuple[str, str]:
    """(public, private) for web push: the public key is what browsers are given, the private one signs our pushes."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    private = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return _b64(public), _b64(private)


def generate() -> dict[str, str]:
    public, private = vapid_pair()
    return {
        "ROUTEBRIDGE_VAPID_PUBLIC_KEY": public,
        "ROUTEBRIDGE_VAPID_PRIVATE_KEY": private,
        "ROUTEBRIDGE_WEBHOOK_SIGNING_SECRET": secrets.token_urlsafe(48),
        "ROUTEBRIDGE_INTERNAL_API_KEY": secrets.token_urlsafe(32),
        "ROUTEBRIDGE_DRIVER_TOKEN_SECRET": secrets.token_urlsafe(48),
    }


if __name__ == "__main__":
    for name, value in generate().items():
        print(f"{name}={value}")
    print("# Also set: ROUTEBRIDGE_DATABASE_URL, ROUTEBRIDGE_REDIS_URL, ROUTEBRIDGE_SMS_API_URL, ROUTEBRIDGE_SMS_API_KEY,")
    print("# ROUTEBRIDGE_S3_ACCESS_KEY, ROUTEBRIDGE_S3_SECRET_KEY, CLERK_SECRET_KEY (values come from your vendors).")
