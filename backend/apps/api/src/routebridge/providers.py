import base64
import html
import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

import httpx

from routebridge.config.settings import get_settings
from routebridge.integrations.circuit import CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodedLocation:
    latitude: float
    longitude: float
    confidence: str
    provider_reference: str | None = None


class MapProvider(Protocol):
    def geocode(self, address: str, landmark: str | None = None) -> GeocodedLocation | None: ...
    def route(self, stops: list[tuple[float, float]]) -> list[int]: ...


class MessagingProvider(Protocol):
    def send(self, recipient: str, body: str) -> str: ...


class PaymentProvider(Protocol):
    def verify(self, provider_reference: str) -> tuple[bool, Decimal]: ...


class CourierPartnerProvider(Protocol):
    def create_job(self, order_reference: str, address: str, amount: Decimal) -> str: ...
    def cancel_job(self, partner_job_id: str) -> None: ...


# ---- messaging -------------------------------------------------------------------------------------------------


class LogMessagingProvider:
    """Development provider: writes the message to the log instead of sending it."""

    def send(self, recipient: str, body: str) -> str:
        logger.info("[sms:log] to=%s body=%s", "*" * max(0, len(recipient) - 4) + recipient[-4:], body)
        return f"log-{uuid4()}"


def _fill(value, mapping: dict[str, str]):
    """Substitute {placeholders} in every string of a JSON-like template."""
    if isinstance(value, str):
        for key, replacement in mapping.items():
            value = value.replace("{" + key + "}", replacement)
        return value
    if isinstance(value, dict):
        return {k: _fill(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, mapping) for v in value]
    return value


class HttpMessagingProvider:
    """JSON-over-HTTPS gateway adapter. The default body is {to, from, channel, message}; a vendor-specific body and
    auth placement can be configured with a payload template and auth style (no code change needed)."""

    def __init__(self, url: str, api_key: str, sender: str, channel: str, breaker: CircuitBreaker, client: httpx.Client | None = None, payload_template: str = "", auth_style: str = "bearer", content_type: str = "json") -> None:
        self.url, self.api_key, self.sender, self.channel, self.breaker = url, api_key, sender, channel, breaker
        if content_type not in {"json", "form"}:
            raise ValueError(f"Unknown content type: {content_type}")
        self.content_type = content_type
        self.client = client or httpx.Client(timeout=10.0)
        self.template = json.loads(payload_template) if payload_template else None
        self.auth_style = auth_style

    def _request_parts(self, recipient: str, body: str) -> tuple[dict, dict]:
        mapping = {"to": recipient, "from": self.sender, "message": body, "channel": self.channel}
        payload = _fill(self.template, mapping) if self.template is not None else {"to": recipient, "from": self.sender, "channel": self.channel, "message": body}
        headers: dict[str, str] = {}
        if self.auth_style == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_style == "basic":
            # HTTP Basic: the key is written "username:password" (Twilio: API key SID, then its secret)
            headers["Authorization"] = "Basic " + base64.b64encode(self.api_key.encode("utf-8")).decode("ascii")
        elif self.auth_style.startswith("header:"):
            headers[self.auth_style.split(":", 1)[1]] = self.api_key
        elif self.auth_style.startswith("body:"):
            payload[self.auth_style.split(":", 1)[1]] = self.api_key
        else:
            raise ValueError(f"Unknown auth style: {self.auth_style}")
        return payload, headers

    def _post(self, recipient: str, body: str) -> str:
        payload, headers = self._request_parts(recipient, body)
        if self.content_type == "form":
            response = self.client.post(self.url, data={key: str(value) for key, value in payload.items()}, headers=headers)  # e.g. Twilio
        else:
            response = self.client.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json() if response.content else {}
        return str(data.get("id") or data.get("sid") or data.get("message_id") or data.get("messageId") or f"{self.channel}-{uuid4()}")

    def send(self, recipient: str, body: str) -> str:
        return self.breaker.call(self._post, recipient, body)


# ---- phone numbers ---------------------------------------------------------------------------------------------

DIAL_CODES = {"NG": "234", "GH": "233", "KE": "254", "ZA": "27", "UG": "256", "TZ": "255", "RW": "250", "SN": "221", "CI": "225", "EG": "20"}


def normalize_phone(raw: str, country: str | None = None) -> str:
    """The international form gateways insist on: +2348012345678 from 08012345678, 2348012345678, 0801 234 5678, +234 801 234 5678 or 8012345678."""
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        return text
    if text.startswith("+"):
        return "+" + digits
    if text.startswith("00") and len(digits) > 6:
        return "+" + digits[2:]
    code = DIAL_CODES.get((country or get_settings().default_country_code).upper(), "234")
    if digits.startswith(code) and len(digits) >= len(code) + 8:
        return "+" + digits
    if digits.startswith("0") and 10 <= len(digits) <= 12:
        return "+" + code + digits[1:]
    if 9 <= len(digits) <= 10:
        return "+" + code + digits
    return "+" + digits


def _gateway_detail(response: httpx.Response) -> str:
    """The reason a gateway gave, in a short readable line (Twilio and Resend both answer with a JSON message)."""
    try:
        data = response.json()
        parts = [str(data.get(key)) for key in ("code", "name") if data.get(key)] + [str(data.get("message") or data.get("error") or "")]
        return " ".join(p for p in parts if p)[:300]
    except Exception:  # noqa: BLE001
        return response.text[:200]


class TwilioMessagingProvider(HttpMessagingProvider):
    """Twilio SMS from just the account SID, auth token and a sender (a number, an approved sender name, or a messaging service)."""

    def __init__(self, account_sid: str, auth_token: str, sender: str, messaging_service_sid: str = "", breaker: CircuitBreaker | None = None, client: httpx.Client | None = None) -> None:
        template = {"To": "{to}", "Body": "{message}"}
        if messaging_service_sid:
            template["MessagingServiceSid"] = messaging_service_sid
        else:
            template["From"] = "{from}"
        super().__init__(
            url=f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json", api_key=f"{account_sid}:{auth_token}", sender=sender, channel="sms",
            breaker=breaker or CircuitBreaker(), client=client, payload_template=json.dumps(template), auth_style="basic", content_type="form",
        )

    def _post(self, recipient: str, body: str) -> str:
        try:
            return super()._post(recipient, body)
        except httpx.HTTPStatusError as exc:
            # say WHY (for example "21608 The number is unverified" on a trial account), not just "HTTP 400"
            raise httpx.HTTPStatusError(f"Twilio refused the message (HTTP {exc.response.status_code}): {_gateway_detail(exc.response)}", request=exc.request, response=exc.response) from exc

    def send(self, recipient: str, body: str) -> str:
        return super().send(normalize_phone(recipient), body)


def twilio_ready(settings=None) -> bool:
    s = settings or get_settings()
    return bool(s.twilio_account_sid and s.twilio_auth_token and (s.twilio_messaging_service_sid or s.twilio_phone_number or s.sms_sender_id))


# ---- email ------------------------------------------------------------------------------------------------------


class LogEmailProvider:
    def send(self, recipient: str, body: str, subject: str = "RouteBridge Logistics") -> str:
        logger.info("[email:log] to=%s subject=%s body=%s", recipient[:2] + "***" + recipient[recipient.find("@"):] if "@" in recipient else "***", subject, body[:200])
        return f"log-{uuid4()}"


RESEND_TEST_SENDER = "RouteBridge Logistics <onboarding@resend.dev>"  # Resend's shared test sender: it only delivers to the Resend account owner


class ResendEmailProvider:
    """Resend (https://resend.com): one JSON call per email. The sender address must belong to a domain verified in Resend."""

    URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str, reply_to: str = "", breaker: CircuitBreaker | None = None, client: httpx.Client | None = None) -> None:
        self.api_key, self.sender, self.reply_to = api_key, sender or RESEND_TEST_SENDER, reply_to
        self.breaker = breaker or CircuitBreaker()
        self.client = client or httpx.Client(timeout=10.0)

    def _post(self, recipient: str, body: str, subject: str) -> str:
        from routebridge.services.email_templates import render_email_html

        payload = {"from": self.sender, "to": [recipient], "subject": subject, "text": body, "html": render_email_html(subject, body)}
        if self.reply_to:
            payload["reply_to"] = self.reply_to
        response = self.client.post(self.URL, json=payload, headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "RouteBridge/1.0"})
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(f"Resend refused the email (HTTP {response.status_code}): {_gateway_detail(response)}", request=response.request, response=response)
        return str(response.json().get("id") or f"email-{uuid4()}")

    def send(self, recipient: str, body: str, subject: str = "RouteBridge Logistics") -> str:
        return self.breaker.call(self._post, recipient, body, subject)


_breakers: dict[str, CircuitBreaker] = {"sms": CircuitBreaker(), "whatsapp": CircuitBreaker(), "geocode": CircuitBreaker(), "email": CircuitBreaker()}


def get_email_provider() -> "ResendEmailProvider | LogEmailProvider":
    s = get_settings()
    if s.email_provider in ("auto", "resend") and s.resend_api_key:
        return ResendEmailProvider(s.resend_api_key, s.email_from, s.email_reply_to, _breakers["email"])
    return LogEmailProvider()


def get_messaging_provider(channel: str) -> MessagingProvider | None:
    settings = get_settings()
    if channel == "whatsapp":
        from routebridge.services.flags import enabled

        if settings.whatsapp_api_url and enabled("whatsapp"):
            return HttpMessagingProvider(settings.whatsapp_api_url, settings.whatsapp_api_key, settings.sms_sender_id, "whatsapp", _breakers["whatsapp"], payload_template=settings.whatsapp_payload_template, auth_style=settings.whatsapp_auth_style, content_type=settings.whatsapp_content_type)
        return None
    if settings.sms_provider == "twilio":
        if not twilio_ready(settings):
            return None  # the sender then records "no provider configured" and retries, instead of pretending
        return TwilioMessagingProvider(settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number or settings.sms_sender_id, settings.twilio_messaging_service_sid, _breakers["sms"])
    if settings.sms_provider == "http" and settings.sms_api_url:
        return HttpMessagingProvider(settings.sms_api_url, settings.sms_api_key, settings.sms_sender_id, "sms", _breakers["sms"], payload_template=settings.sms_payload_template, auth_style=settings.sms_auth_style, content_type=settings.sms_content_type)
    return LogMessagingProvider()


# ---- geocoding -------------------------------------------------------------------------------------------------


class NominatimGeocoder:
    """OpenStreetMap Nominatim adapter with an in-process cache, circuit breaker and graceful failure."""

    def __init__(self, url: str, breaker: CircuitBreaker, client: httpx.Client | None = None) -> None:
        self.url, self.breaker = url, breaker
        self.client = client or httpx.Client(timeout=8.0, headers={"User-Agent": "RouteBridge/0.1"})
        self._cache: dict[str, GeocodedLocation | None] = {}

    def _lookup(self, query: str) -> GeocodedLocation | None:
        response = self.client.get(self.url, params={"q": query, "format": "json", "limit": 1, "countrycodes": "ng"})
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        return GeocodedLocation(float(rows[0]["lat"]), float(rows[0]["lon"]), "geocoded", str(rows[0].get("place_id", "")) or None)

    def geocode(self, address: str, landmark: str | None = None) -> GeocodedLocation | None:
        query = ", ".join(part for part in (landmark, address) if part)
        if query in self._cache:
            return self._cache[query]
        try:
            result = self.breaker.call(self._lookup, query)
        except Exception:
            logger.warning("Geocoder unavailable; falling back to manual coordinates", exc_info=True)
            return None
        self._cache[query] = result
        return result

    def route(self, stops: list[tuple[float, float]]) -> list[int]:
        from routebridge.services.routing import sequence_stops

        return sequence_stops(stops)


_geocoder: MapProvider | None = None


def get_geocoder() -> MapProvider | None:
    global _geocoder
    from routebridge.services.flags import enabled

    settings = get_settings()
    if settings.geocoder_provider == "nominatim" and enabled("geocoding"):
        if _geocoder is None:
            _geocoder = NominatimGeocoder(settings.geocoder_url, _breakers["geocode"])
        return _geocoder
    return None


# ---- masked calling --------------------------------------------------------------------------------------------


class TelephonyProvider(Protocol):
    def bridge_call(self, driver_phone: str, customer_phone: str, reference: str) -> str: ...


class LogTelephonyProvider:
    def bridge_call(self, driver_phone: str, customer_phone: str, reference: str) -> str:
        logger.info("[call:log] bridging driver and customer for %s", reference)  # numbers are never logged
        return f"log-call-{uuid4()}"


class HttpTelephonyProvider:
    """Asks a telephony gateway to ring the driver and customer through proxy numbers (neither sees the other's number)."""

    def __init__(self, url: str, api_key: str, breaker: CircuitBreaker, client: httpx.Client | None = None) -> None:
        self.url, self.api_key, self.breaker = url, api_key, breaker
        self.client = client or httpx.Client(timeout=10.0)

    def _post(self, driver_phone: str, customer_phone: str, reference: str) -> str:
        response = self.client.post(self.url, json={"party_a": driver_phone, "party_b": customer_phone, "reference": reference}, headers={"Authorization": f"Bearer {self.api_key}"})
        response.raise_for_status()
        data = response.json() if response.content else {}
        return str(data.get("id") or data.get("session_id") or f"call-{uuid4()}")

    def bridge_call(self, driver_phone: str, customer_phone: str, reference: str) -> str:
        return self.breaker.call(self._post, driver_phone, customer_phone, reference)


_breakers["telephony"] = CircuitBreaker()


def get_telephony_provider() -> TelephonyProvider:
    settings = get_settings()
    if settings.telephony_provider == "http" and settings.telephony_api_url:
        return HttpTelephonyProvider(settings.telephony_api_url, settings.telephony_api_key, _breakers["telephony"])
    return LogTelephonyProvider()
