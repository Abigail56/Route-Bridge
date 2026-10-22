import json
import re
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def as_text_list(value):
    """Read a list setting the way people really type it.

    The strict form is a JSON list: ["user_abc", "user_def"]. Hosting dashboards invite mistakes (no brackets, no quotes, a comma list,
    stray spaces), and one wrong character used to stop the whole API from starting, so all of these are accepted:
    ["a"] , [a] , a , a,b , a b , "a" , empty.
    """
    if value is None:
        return []
    if not isinstance(value, str):
        return list(value)
    text = value.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    parts = re.split(r"[,\s]+", text.strip("[]"))
    return [part.strip("\"'") for part in parts if part.strip("\"'")]


class Settings(BaseSettings):
    """Environment-backed application configuration."""

    app_name: str = "RouteBridge API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./routebridge.db"
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    default_country_code: str = "NG"
    default_currency: str = "NGN"
    default_timezone: str = "Africa/Lagos"
    require_api_key: bool = False
    internal_api_key: str = ""
    # Sign-in (our own, no outside service): session tokens are HS256-signed with this secret and kept in an httpOnly cookie.
    # Make one with `python -m routebridge.tools.gen_secrets`. Changing it signs everybody out.
    session_secret: str = ""
    session_max_hours: int = 12
    # "Keep me signed in on this device" on the sign-in page: that session lasts this many days instead (0 = the box is not offered)
    session_remember_days: int = 30
    # the website's address: where people land after Google sign-in and what password-reset links point to
    web_base_url: str = "http://localhost:3000"
    # "Continue with Google" (Google Cloud Console > APIs & Services > Credentials > OAuth client, type Web application).
    # The redirect URI registered there must equal google_redirect_uri; empty = <web_base_url>/api/v1/auth/google/callback.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    auth_attempt_limit: int = 5
    auth_attempt_window_seconds: int = 900
    redis_url: str = ""
    webhook_signing_secret: str = ""
    verify_webhook_signatures: bool = False
    # off only for local development without sign-in; ROUTEBRIDGE_REQUIRE_CLERK_AUTH is the old name and still read
    require_auth: bool = Field(default=False, validation_alias=AliasChoices("ROUTEBRIDGE_REQUIRE_AUTH", "ROUTEBRIDGE_REQUIRE_CLERK_AUTH"))
    # user ids allowed to run the platform (bootstrap list; more are added in the Platform console). Empty = nobody outside dev/test.
    platform_admin_subjects: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # the same by email, but only for an account whose email is proven (signed in with Google, or reset its password by email),
    # so nobody becomes an admin by typing the admin's address into the sign-up form
    platform_admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # the company that receives "Send to the Admin" join requests from new shops and riders; empty = the only active workspace
    join_requests_tenant_id: UUID | None = None
    require_postgis: bool = False
    max_outbox_attempts: int = 8
    # Public tracking / notifications
    public_tracking_base_url: str = "http://localhost:3000/track"
    tracking_token_ttl_days: int = 30
    billing_enforced: bool = False  # when true, plan limits and expiry are enforced (leave off until you are ready to charge)
    # shops must pay their own plan online once their trial ends (only possible while a Paystack key is set)
    shop_billing_enforced: bool = True
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
    # a delivery can only be completed with the customer's code, checked by the server (a photo alone is not enough)
    require_delivery_code: bool = False

    @field_validator("database_url")
    @classmethod
    def _driver_in_database_url(cls, value: str) -> str:
        """Hosts hand out postgres://... or postgresql://...; this app talks to PostgreSQL through psycopg 3."""
        for plain in ("postgres://", "postgresql://"):
            if value.startswith(plain):
                return "postgresql+psycopg://" + value[len(plain):]
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _origins(cls, value):
        return [origin.rstrip("/") for origin in as_text_list(value)]  # a website address never ends with a slash here

    @field_validator("platform_admin_subjects", mode="before")
    @classmethod
    def _admins(cls, value):
        return as_text_list(value)

    @field_validator("platform_admin_emails", mode="before")
    @classmethod
    def _admin_emails(cls, value):
        return [email.strip().lower() for email in as_text_list(value)]

    @field_validator("join_requests_tenant_id", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value  # an empty line in .env means "not set"

    @field_validator("web_base_url")
    @classmethod
    def _web_base(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_callback_url(self) -> str:
        return self.google_redirect_uri or f"{self.web_base_url}/api/v1/auth/google/callback"

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
