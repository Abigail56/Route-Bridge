"""Refuse to start a non-development deployment with unsafe or incomplete configuration."""
from routebridge.config.settings import Settings

DEV_ENVIRONMENTS = {"development", "test"}


def production_problems(settings: Settings) -> list[str]:
    """Human-readable list of configuration problems; empty when the settings are safe for a real deployment."""
    if settings.environment in DEV_ENVIRONMENTS:
        return []
    problems: list[str] = []
    if not settings.database_url.startswith(("postgresql", "postgres")):
        problems.append("ROUTEBRIDGE_DATABASE_URL must be PostgreSQL")
    if not settings.require_clerk_auth or not settings.clerk_jwks_url or not settings.clerk_issuer:
        problems.append("Clerk auth must be enforced: set ROUTEBRIDGE_REQUIRE_CLERK_AUTH=true, ROUTEBRIDGE_CLERK_JWKS_URL and ROUTEBRIDGE_CLERK_ISSUER")
    if settings.require_clerk_auth and not settings.clerk_webhook_secret.startswith("whsec_"):
        problems.append("Set ROUTEBRIDGE_CLERK_WEBHOOK_SECRET (whsec_..., from Clerk Dashboard > Webhooks) so Clerk can sync users")
    if not settings.redis_url:
        problems.append("ROUTEBRIDGE_REDIS_URL is required (rate limits and the live event stream)")
    if not settings.verify_webhook_signatures or len(settings.webhook_signing_secret) < 32:
        problems.append("Set ROUTEBRIDGE_VERIFY_WEBHOOK_SIGNATURES=true and a ROUTEBRIDGE_WEBHOOK_SIGNING_SECRET of at least 32 characters")
    if settings.require_api_key and not settings.internal_api_key:
        problems.append("ROUTEBRIDGE_REQUIRE_API_KEY is on but ROUTEBRIDGE_INTERNAL_API_KEY is empty")
    if not settings.internal_api_key:
        problems.append("ROUTEBRIDGE_INTERNAL_API_KEY is required to protect /metrics")
    if settings.driver_token_secret and len(settings.driver_token_secret) < 32:
        problems.append("ROUTEBRIDGE_DRIVER_TOKEN_SECRET must be at least 32 characters when set")
    if not settings.driver_token_secret:
        problems.append("ROUTEBRIDGE_DRIVER_TOKEN_SECRET is required (driver devices cannot authenticate without it)")
    for origin in settings.allowed_origins:
        if origin == "*" or "localhost" in origin or "127.0.0.1" in origin or origin.endswith(".example"):
            problems.append(f"ROUTEBRIDGE_ALLOWED_ORIGINS contains a non-production origin: {origin}")
    if (settings.sms_provider == "log" and not settings.allow_log_sms) or (settings.sms_provider == "http" and not (settings.sms_api_url and settings.sms_api_key)):
        problems.append("SMS is not configured: set ROUTEBRIDGE_SMS_PROVIDER=http with ROUTEBRIDGE_SMS_API_URL and ROUTEBRIDGE_SMS_API_KEY (the 'log' provider never sends)")
    if settings.sms_provider == "http" and any("PUT_" in value for value in (settings.sms_api_url, settings.sms_api_key, settings.sms_sender_id)):
        problems.append("SMS settings still contain a PUT_... placeholder (account id or sender number): fill in the real Twilio/gateway values")
    if settings.sms_provider == "http" and not settings.sms_sender_id.strip():
        problems.append("ROUTEBRIDGE_SMS_SENDER_ID is empty: messages need a sender (a Twilio number or an approved sender name)")
    if settings.media_provider == "s3" and not (settings.s3_endpoint and settings.s3_bucket and settings.s3_access_key and settings.s3_secret_key):
        problems.append("ROUTEBRIDGE_MEDIA_PROVIDER=s3 needs S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY and S3_SECRET_KEY")
    if settings.media_provider == "local":
        problems.append("ROUTEBRIDGE_MEDIA_PROVIDER=local stores delivery photos on one node's disk; use s3 in production")
    if "localhost" in settings.public_tracking_base_url:
        problems.append("ROUTEBRIDGE_PUBLIC_TRACKING_BASE_URL points at localhost; customers would receive broken links")
    return problems


def validate_production_settings(settings: Settings) -> None:
    problems = production_problems(settings)
    if problems:
        raise RuntimeError("Unsafe production configuration:\n - " + "\n - ".join(problems))
