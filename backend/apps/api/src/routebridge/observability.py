"""Request correlation, structured access logs and Prometheus-style metrics (no extra dependencies)."""
import json
import logging
import time
from collections import defaultdict
from contextvars import ContextVar
from threading import Lock
from uuid import uuid4

from fastapi import Request

logger = logging.getLogger("routebridge.access")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_lock = Lock()
_requests: dict[tuple[str, str], int] = defaultdict(int)
_latency_sum: dict[str, float] = defaultdict(float)
_latency_count: dict[str, int] = defaultdict(int)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"  # templated path keeps label cardinality low


async def observe_requests(request: Request, call_next):
    """Attach a correlation id, emit one JSON access-log line and record metrics."""
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        elapsed = time.perf_counter() - started
        label = _route_label(request)
        with _lock:
            _requests[(label, f"{status_code // 100}xx")] += 1
            _latency_sum[label] += elapsed
            _latency_count[label] += 1
        logger.info(json.dumps({"request_id": request_id, "method": request.method, "route": label, "status": status_code, "duration_ms": round(elapsed * 1000, 1)}))
        request_id_var.reset(token)


def render_metrics(gauges: dict[str, float]) -> str:
    lines = ["# TYPE routebridge_http_requests_total counter"]
    with _lock:
        for (route, klass), count in sorted(_requests.items()):
            lines.append(f'routebridge_http_requests_total{{route="{route}",status="{klass}"}} {count}')
        lines.append("# TYPE routebridge_http_request_seconds_sum counter")
        for route, total in sorted(_latency_sum.items()):
            lines.append(f'routebridge_http_request_seconds_sum{{route="{route}"}} {total:.6f}')
            lines.append(f'routebridge_http_request_seconds_count{{route="{route}"}} {_latency_count[route]}')
    for name, value in sorted(gauges.items()):
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")
    return "\n".join(lines) + "\n"
