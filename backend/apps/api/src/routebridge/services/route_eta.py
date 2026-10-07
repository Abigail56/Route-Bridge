"""Road-based arrival times from a routing service, with the plain straight-line estimate as the safety net.

ROUTEBRIDGE_ROUTE_PROVIDER:
  none    (default) nothing is called; callers use the straight-line estimate in services/tracking.py
  osrm    road distances from an OSRM server (no live traffic)
  mapbox  the `driving-traffic` profile, which includes current traffic (needs ROUTEBRIDGE_ROUTE_API_KEY)

Every failure (service down, bad key, slow answer) returns None so the caller falls back; the circuit breaker stops us hammering a service that is down.
Answers are remembered briefly because a rider's dot is refreshed every few seconds.
"""
import logging
from threading import Lock
from time import monotonic

import httpx

from routebridge.config.settings import get_settings
from routebridge.integrations.circuit import CircuitBreaker

log = logging.getLogger(__name__)
CACHE_SECONDS = 90
MAX_CACHE = 2000
_breaker = CircuitBreaker(failure_threshold=4, reset_seconds=60)
_cache: dict[tuple, tuple[float, int]] = {}
_lock = Lock()
_client: httpx.Client | None = None  # tests replace this with a client on a mock transport


def reset() -> None:
    global _breaker
    _breaker = CircuitBreaker(failure_threshold=4, reset_seconds=60)
    with _lock:
        _cache.clear()


def provider_enabled() -> bool:
    settings = get_settings()
    return settings.route_provider == "osrm" or (settings.route_provider == "mapbox" and bool(settings.route_api_key))


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=3.0)
    return _client


def _fetch(origin: tuple[float, float], dest: tuple[float, float]) -> int:
    settings = get_settings()
    coords = f"{origin[1]:.6f},{origin[0]:.6f};{dest[1]:.6f},{dest[0]:.6f}"
    if settings.route_provider == "mapbox":
        response = _http().get(f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords}", params={"overview": "false", "access_token": settings.route_api_key})
    else:
        response = _http().get(f"{settings.route_osrm_url.rstrip('/')}/route/v1/driving/{coords}", params={"overview": "false"})
    response.raise_for_status()
    routes = response.json().get("routes") or []
    if not routes:
        raise ValueError("no route found")
    return max(1, round(float(routes[0]["duration"]) / 60))


def travel_minutes(origin: tuple[float, float], dest: tuple[float, float]) -> int | None:
    """Minutes by road, or None when no provider is set or it cannot answer right now."""
    if not provider_enabled():
        return None
    key = (round(origin[0], 3), round(origin[1], 3), round(dest[0], 4), round(dest[1], 4), get_settings().route_provider)
    now = monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    try:
        minutes = _breaker.call(_fetch, origin, dest)
    except Exception as exc:  # noqa: BLE001 - includes the open circuit; the caller has a fallback
        log.warning("route lookup failed (%s); using the straight-line estimate", type(exc).__name__)
        return None
    with _lock:
        if len(_cache) >= MAX_CACHE:
            _cache.clear()
        _cache[key] = (now, minutes)
    return minutes
