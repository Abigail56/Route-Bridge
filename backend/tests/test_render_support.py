import threading

import pytest

from routebridge.config.settings import Settings
from routebridge.config.validation import production_problems
from routebridge.workers import embedded


@pytest.mark.parametrize("given", ["postgres://u:p@dpg-1/db", "postgresql://u:p@dpg-1/db", "postgresql+psycopg://u:p@dpg-1/db"])
def test_the_database_address_a_host_provides_gets_the_right_driver(given: str) -> None:
    assert Settings(database_url=given, _env_file=None).database_url == "postgresql+psycopg://u:p@dpg-1/db"


def test_sqlite_addresses_are_left_alone() -> None:
    assert Settings(database_url="sqlite:///./x.db", _env_file=None).database_url == "sqlite:///./x.db"


def _prod(**overrides) -> Settings:
    base = dict(
        environment="production", database_url="postgresql+psycopg://u:p@db/rb", require_clerk_auth=True, clerk_webhook_secret="whsec_dGVzdC1zZWNyZXQ=",
        clerk_jwks_url="https://clerk.test/jwks", clerk_issuer="https://clerk.test", redis_url="redis://r:6379/0", verify_webhook_signatures=True,
        webhook_signing_secret="w" * 32, internal_api_key="i" * 24, driver_token_secret="d" * 32, allowed_origins=["https://app.example.test"],
        sms_provider="log", allow_log_sms=True, media_provider="local", public_tracking_base_url="https://app.example.test/track",
    )
    return Settings(**{**base, **overrides}, _env_file=None)


def test_local_photo_storage_is_refused_unless_it_was_knowingly_allowed() -> None:
    assert [p for p in production_problems(_prod()) if "MEDIA" in p]
    assert not [p for p in production_problems(_prod(allow_local_media=True)) if "MEDIA" in p]
    assert not production_problems(_prod(allow_local_media=True))


def test_embedded_workers_start_once_and_only_when_switched_on(monkeypatch) -> None:
    started = []
    release = threading.Event()
    monkeypatch.setattr(embedded, "_targets", lambda: [("a", lambda: started.append("a") or release.wait(5)), ("b", lambda: started.append("b") or release.wait(5))])
    monkeypatch.setattr(embedded, "_started", False)

    settings = embedded.get_settings()
    monkeypatch.setattr(settings, "embedded_workers", False)
    assert embedded.start_embedded_workers() == []  # off by default

    monkeypatch.setattr(settings, "embedded_workers", True)
    threads = embedded.start_embedded_workers()
    assert [t.name for t in threads] == ["embedded-a", "embedded-b"] and all(t.daemon for t in threads)
    assert embedded.start_embedded_workers() == []  # a second call must not start copies
    for t in threads:
        t.join(0.3)
    assert sorted(started) == ["a", "b"]
    release.set()
