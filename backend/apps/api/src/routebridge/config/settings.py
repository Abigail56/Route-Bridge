from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
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
    billing_enforced: bool = False  # when true, plan limits and expiry are enforced (leave off until you are ready to charge)
    paystack_secret_key: str = ""
    paystack_callback_url: str = ""  # where Paystack sends the customer back; default is the Settings page of the first allowed origin
    # web push for drivers (make the pair with `python -m routebridge.tools.gen_secrets`)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@routebridge.local"
    # arrival times by road: none | osrm | mapbox (mapbox includes live traffic and needs route_api_key)
    route_provider: str = "none"
    route_api_key: str = ""
    route_osrm_url: str = "https://router.project-osrm.org"
    eta_speed_kmh: float = 22.0  # average city speed used for the 'about N minutes away' estimate
    auto_assign_radius_km: float = 15.0  # farthest a driver may be from the drop-off for automatic assignment
    sms_provider: str = "log"  # log | twilio | http
    # --- Twilio: fill these in and the app builds the whole request itself (the plain names TWILIO_* work too) ---
    twilio_account_sid: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_TWILIO_ACCOUNT_SID", "TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_TWILIO_AUTH_TOKEN", "TWILIO_AUTH_TOKEN"))
    twilio_phone_number: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_TWILIO_PHONE_NUMBER", "TWILIO_PHONE_NUMBER"))
    twilio_messaging_service_sid: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_TWILIO_MESSAGING_SERVICE_SID", "TWILIO_MESSAGING_SERVICE_SID"))
    # --- email through Resend (RESEND_API_KEY and EMAIL_FROM work as plain names) ---
    email_provider: str = Field(default="auto", validation_alias=AliasChoices("ROUTEBRIDGE_EMAIL_PROVIDER", "EMAIL_PROVIDER"))  # auto | resend | log
    resend_api_key: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_RESEND_API_KEY", "RESEND_API_KEY"))
    email_from: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_EMAIL_FROM", "EMAIL_FROM"))
    email_reply_to: str = Field(default="", validation_alias=AliasChoices("ROUTEBRIDGE_EMAIL_REPLY_TO", "EMAIL_REPLY_TO"))
    # lets a deployment run knowingly WITHOUT real texts (a pilot before an SMS account exists); the production check otherwise refuses 'log'
    allow_log_sms: bool = False
    # how the driver reaches the customer once arrived: direct = the phone's own dialer (works with no phone service),
    # masked = a bridged call through the telephony gateway (numbers stay hidden), auto = masked when a gateway is configured, else direct
    driver_call_mode: str = "auto"
    # same idea for delivery photos: a pilot without object storage keeps them on this server's disk (lost when it is rebuilt)
    allow_local_media: bool = False
    # run the outbox, notification and maintenance workers inside the API process (hosting that charges per worker, like Render's free plan)
    embedded_workers: bool = False
    sms_api_url: str = ""
    sms_api_key: str = ""
    sms_sender_id: str = "RouteBridge"
    # Vendor adapters: JSON body with {to} {from} {message} {channel} placeholders, and where the API key goes:
    # "bearer" (Authorization header), "header:<Name>" (custom header) or "body:<field>" (merged into the JSON body).
    sms_payload_template: str = ""
    sms_auth_style: str = "bearer"  # bearer | basic | header:<Name> | body:<field>
    sms_content_type: str = "json"  # json | form (Twilio uses form)
    whatsapp_api_url: str = ""
    whatsapp_api_key: str = ""
    whatsapp_payload_template: str = ""
    whatsapp_auth_style: str = "bearer"
    whatsapp_content_type: str = "json"
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
    # how the customer gets the delivery code: sms = texted automatically; dashboard = staff pass it on by hand (no SMS sender needed)
    otp_delivery: str = "sms"

    @field_validator("database_url")
    @classmethod
    def _driver_in_database_url(cls, value: str) -> str:
        """Hosts hand out postgres://... or postgresql://...; this app talks to PostgreSQL through psycopg 3."""
        for plain in ("postgres://", "postgresql://"):
            if value.startswith(plain):
                return "postgresql+psycopg://" + value[len(plain):]
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ROUTEBRIDGE_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
