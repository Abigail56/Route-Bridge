from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application configuration."""

    app_name: str = "RouteBridge API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./routebridge.db"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    default_country_code: str = "NG"
    default_currency: str = "NGN"
    default_timezone: str = "Africa/Lagos"
    require_api_key: bool = False
    internal_api_key: str = ""
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    auth_attempt_limit: int = 5
    auth_attempt_window_seconds: int = 900
    redis_url: str = ""
    webhook_signing_secret: str = ""
    verify_webhook_signatures: bool = False
    require_clerk_auth: bool = False
    # Clerk webhook signing secret (Svix, starts with whsec_) from Clerk Dashboard > Webhooks. Used to sync users.
    clerk_webhook_secret: str = ""
    # Clerk subjects allowed to create tenants (platform operators). Empty = nobody outside dev/test.
    platform_admin_subjects: list[str] = Field(default_factory=list)
    require_postgis: bool = False
    max_outbox_attempts: int = 8
    # Public tracking / notifications
    public_tracking_base_url: str = "http://localhost:3000/track"
    tracking_token_ttl_days: int = 30
    sms_provider: str = "log"  # log | http
    sms_api_url: str = ""
    sms_api_key: str = ""
    sms_sender_id: str = "RouteBridge"
    # Vendor adapters: JSON body with {to} {from} {message} {channel} placeholders, and where the API key goes:
    # "bearer" (Authorization header), "header:<Name>" (custom header) or "body:<field>" (merged into the JSON body).
    sms_payload_template: str = ""
    sms_auth_style: str = "bearer"
    whatsapp_api_url: str = ""
    whatsapp_api_key: str = ""
    whatsapp_payload_template: str = ""
    whatsapp_auth_style: str = "bearer"
    # Masked calling: the provider bridges driver and customer through proxy numbers; neither sees the other's number.
    telephony_provider: str = "log"  # log | http
    telephony_api_url: str = ""
    telephony_api_key: str = ""
    # Delivery photos / signatures
    media_provider: str = "local"  # local | s3
    media_dir: str = "./media"
    s3_endpoint: str = ""  # e.g. https://s3.af-south-1.amazonaws.com or a MinIO URL
    s3_bucket: str = ""
    s3_region: str = "af-south-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    media_url_ttl_seconds: int = 900
    # Runtime feature switches, e.g. ROUTEBRIDGE_FEATURE_FLAGS={"customer_corrections": false}
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    geocoder_provider: str = "none"  # none | nominatim
    geocoder_url: str = "https://nominatim.openstreetmap.org/search"
    # Driver device tokens (short-lived, HS256)
    driver_token_secret: str = ""
    driver_token_ttl_minutes: int = 720
    otp_ttl_minutes: int = 30
    otp_max_attempts: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ROUTEBRIDGE_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
