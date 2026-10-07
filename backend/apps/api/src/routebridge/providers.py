import base64
import json
import logging
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


_breakers: dict[str, CircuitBreaker] = {"sms": CircuitBreaker(), "whatsapp": CircuitBreaker(), "geocode": CircuitBreaker()}


def get_messaging_provider(channel: str) -> MessagingProvider | None:
    settings = get_settings()
    if channel == "whatsapp":
        from routebridge.services.flags import enabled

        if settings.whatsapp_api_url and enabled("whatsapp"):
            return HttpMessagingProvider(settings.whatsapp_api_url, settings.whatsapp_api_key, settings.sms_sender_id, "whatsapp", _breakers["whatsapp"], payload_template=settings.whatsapp_payload_template, auth_style=settings.whatsapp_auth_style, content_type=settings.whatsapp_content_type)
        return None
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
