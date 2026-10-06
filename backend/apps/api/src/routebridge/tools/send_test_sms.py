"""Send ONE test SMS through the configured gateway, to check credentials, sender id and request format.

    python -m routebridge.tools.send_test_sms +2348012345678 ["optional message"]

Run it from backend/apps/api so the .env file is loaded. It prints which provider is active, the request fields it will
use (never the API key) and the gateway's answer. With ROUTEBRIDGE_SMS_PROVIDER=log nothing is sent.
"""
import json
import sys

import httpx

from routebridge.config.settings import get_settings
from routebridge.providers import HttpMessagingProvider, get_messaging_provider


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    recipient = argv[0]
    body = argv[1] if len(argv) > 1 else "RouteBridge test message. If you can read this, SMS delivery works."
    settings = get_settings()
    provider = get_messaging_provider("sms")
    masked = "*" * max(0, len(recipient) - 4) + recipient[-4:]
    print(f"provider: {settings.sms_provider} ({type(provider).__name__}) | to: {masked} | sender id: {settings.sms_sender_id or '(empty)'}")
    if settings.sms_provider != "http":
        print("ROUTEBRIDGE_SMS_PROVIDER is not 'http', so this only logs the message and sends nothing.")
    elif isinstance(provider, HttpMessagingProvider):
        payload, _ = provider._request_parts(recipient, body)
        shown = {k: ("<hidden>" if "key" in k.lower() else v) for k, v in payload.items()}
        print("request body:", json.dumps(shown))
        if not settings.sms_sender_id:
            print("warning: no sender id is set; most gateways reject messages without a registered one.")
    try:
        message_id = provider.send(recipient, body)
    except httpx.HTTPStatusError as exc:
        print(f"gateway rejected the request: HTTP {exc.response.status_code}: {exc.response.text[:300]}")
        return 1
    except Exception as exc:  # network failure, open circuit, bad template
        print(f"could not send: {type(exc).__name__}: {exc}")
        return 1
    print(f"accepted by the gateway, message id: {message_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
