"""Tiny circuit breaker used around outbound providers (maps, messaging, payments)."""
from threading import Lock
from time import monotonic


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if monotonic() - self._opened_at >= self.reset_seconds:
                return False  # half-open: allow one trial call
            return True

    def call(self, fn, *args, **kwargs):
        if self.is_open:
            raise CircuitOpenError("circuit open")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = monotonic()
            raise
        with self._lock:
            self._failures = 0
            self._opened_at = None
        return result
