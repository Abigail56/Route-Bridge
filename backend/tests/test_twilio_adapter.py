import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from routebridge.integrations.circuit import CircuitBreaker
from routebridge.providers import HttpMessagingProvider

URL = "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json"
TEMPLATE = json.dumps({"To": "{to}", "From": "{from}", "Body": "{message}"})


def provider(handler, **overrides) -> HttpMessagingProvider:
    options = dict(url=URL, api_key="SKkeysid:the-secret", sender="+15005550006", channel="sms", breaker=CircuitBreaker(), payload_template=TEMPLATE, auth_style="basic", content_type="form")
    options.update(overrides)
    return HttpMessagingProvider(client=httpx.Client(transport=httpx.MockTransport(handler)), **options)


def test_a_twilio_message_is_a_form_post_with_basic_login() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["type"] = request.headers["content-type"]
        seen["form"] = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        return httpx.Response(201, json={"sid": "SM123", "status": "queued"})

    message_id = provider(handler).send("+2348031234567", "Your parcel is on the way. Code 4821.")
    assert message_id == "SM123"  # Twilio calls its message id "sid"
    assert seen["url"] == URL
    assert seen["type"].startswith("application/x-www-form-urlencoded")
    assert seen["form"] == {"To": "+2348031234567", "From": "+15005550006", "Body": "Your parcel is on the way. Code 4821."}
    scheme, encoded = seen["auth"].split(" ", 1)
    assert scheme == "Basic" and base64.b64decode(encoded).decode() == "SKkeysid:the-secret"


def test_json_gateways_still_work_unchanged() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message_id": "abc"})

    result = provider(handler, auth_style="bearer", content_type="json", payload_template="", api_key="token").send("+2348031234567", "hi")
    assert result == "abc" and seen["auth"] == "Bearer token" and seen["body"]["message"] == "hi"


def test_an_unknown_content_type_is_refused_early() -> None:
    with pytest.raises(ValueError):
        provider(lambda request: httpx.Response(200), content_type="xml")


def test_a_twilio_error_is_reported_not_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 20003, "message": "Authenticate"})

    with pytest.raises(httpx.HTTPStatusError):
        provider(handler).send("+2348031234567", "hi")


def test_the_production_check_refuses_a_placeholder_sender_or_account() -> None:
    from routebridge.config.settings import Settings
    from routebridge.config.validation import production_problems

    base = dict(environment="production", database_url="postgresql+psycopg://u:p@h/db", sms_provider="http", sms_api_url="https://api.twilio.com/2010-04-01/Accounts/ACabc/Messages.json", sms_api_key="ACabc:token", sms_sender_id="+15005550006")
    assert not [p for p in production_problems(Settings(**base)) if "SMS" in p]
    placeholder = [p for p in production_problems(Settings(**{**base, "sms_sender_id": "PUT_YOUR_TWILIO_NUMBER_OR_APPROVED_SENDER_HERE"})) if "placeholder" in p]
    assert placeholder
    assert [p for p in production_problems(Settings(**{**base, "sms_sender_id": " "})) if "SENDER_ID" in p]
