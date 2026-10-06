from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status
from redis import Redis

from routebridge.config.settings import get_settings


@dataclass
class _Window:
    started_at: float
    attempts: int


class InMemoryRateLimiter:
    """Development limiter; use Redis for multi-instance production deployments."""

    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> int:
        now = monotonic()
        with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= window_seconds:
                self._windows[key] = _Window(now, 1)
                return 0
            if window.attempts >= limit:
                return max(1, int(window_seconds - (now - window.started_at)))
            window.attempts += 1
            return 0


limiter = InMemoryRateLimiter()


def _redis_retry_after(key: str, limit: int, window_seconds: int) -> int:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, window_seconds)
    if count > limit:
        return max(1, int(client.ttl(key)))
    return 0


def enforce_auth_attempt(key: str, limit: int, window_seconds: int) -> None:
    settings = get_settings()
    if not settings.redis_url and settings.environment not in {"development", "test"}:
        raise HTTPException(status_code=503, detail="Redis rate limiting is required in this environment")
    if settings.redis_url:
        try:
            retry_after = _redis_retry_after(key, limit, window_seconds)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Rate-limit service unavailable") from exc
    else:
        retry_after = limiter.check(key, limit, window_seconds)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many authentication attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
