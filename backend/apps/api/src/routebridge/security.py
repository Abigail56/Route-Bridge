from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from routebridge.config.settings import get_settings
from routebridge.integrations.clerk import verify_clerk_token


PUBLIC_PATHS = {"/health", "/ready", "/docs", "/redoc", "/openapi.json"}
PUBLIC_API_PREFIXES = ("/api/v1/auth/signin", "/api/v1/auth/signup", "/api/v1/webhooks", "/api/v1/public", "/api/v1/driver")


async def api_key_guard(request: Request, call_next: Callable[[Request], Awaitable]):
    settings = get_settings()
    if settings.environment not in {"development", "test"} and request.url.path.startswith("/api/v1") and not request.url.path.startswith(PUBLIC_API_PREFIXES):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Bearer token required"})
        try:
            request.state.clerk_user = verify_clerk_token(authorization.removeprefix("Bearer ").strip())
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Invalid Clerk token"})
    if settings.require_api_key and request.url.path not in PUBLIC_PATHS and not request.url.path.startswith(PUBLIC_API_PREFIXES) and getattr(request.state, "clerk_user", None) is None:
        supplied = request.headers.get("X-API-Key", "")
        if not settings.internal_api_key or supplied != settings.internal_api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)
