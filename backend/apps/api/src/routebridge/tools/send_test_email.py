"""Send ONE test email through Resend, to check the key and the sender address.

    docker compose exec -T api python -m routebridge.tools.send_test_email you@example.com

Until you verify a domain in Resend, only the address of your own Resend account can receive mail. The answer from Resend is printed.
"""
import sys

import httpx

from routebridge.config.settings import get_settings
from routebridge.providers import ResendEmailProvider, get_email_provider


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    recipient = argv[0]
    settings = get_settings()
    provider = get_email_provider()
    print(f"provider: {type(provider).__name__} | to: {recipient} | from: {getattr(provider, 'sender', '(log only)')}")
    if not isinstance(provider, ResendEmailProvider):
        print("No Resend key is set (RESEND_API_KEY), or EMAIL_PROVIDER=log, so this only writes to the log and sends nothing.")
    try:
        message_id = provider.send(recipient, "This is a test from RouteBridge Logistics.\n\nIf you can read this, email delivery works.", subject="RouteBridge test email")
    except httpx.HTTPStatusError as exc:
        print(f"Resend refused it: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"could not send: {type(exc).__name__}: {exc}")
        return 1
    print(f"accepted. id: {message_id}")
    return 0 if settings.resend_api_key else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
