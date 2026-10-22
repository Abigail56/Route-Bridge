from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from routebridge.config.settings import get_settings
from routebridge.integrations.sessions import token_from_request, verify_session_token


PUBLIC_PATHS = {"/health", "/ready", "/docs", "/redoc", "/openapi.json"}
# signing in, registering, password reset and the Google round trip happen before anyone has a session
PUBLIC_API_PREFIXES = ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/logout", "/api/v1/auth/session", "/api/v1/auth/password/", "/api/v1/auth/google/", "/api/v1/auth/providers", "/api/v1/webhooks", "/api/v1/public", "/api/v1/driver")


async def api_key_guard(request: Request, call_next: Callable[[Request], Awaitable]):
    settings = get_settings()
    if settings.environment not in {"development", "test"} and request.url.path.startswith("/api/v1") and not request.url.path.startswith(PUBLIC_API_PREFIXES):
        token = token_from_request(request)
        if token is None:
            return JSONResponse(status_code=401, content={"detail": "Sign in required"})
        try:
            request.state.clerk_user = verify_session_token(token)
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Session expired or invalid. Sign in again."})
    if settings.require_api_key and request.url.path not in PUBLIC_PATHS and not request.url.path.startswith(PUBLIC_API_PREFIXES) and getattr(request.state, "clerk_user", None) is None:
        supplied = request.headers.get("X-API-Key", "")
        if not settings.internal_api_key or supplied != settings.internal_api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)
