"""Hosting dashboards invite typing mistakes in list settings; one wrong character must not stop the API from starting."""
import pytest

from routebridge.config.settings import Settings, as_text_list


@pytest.mark.parametrize(
    "typed, expected",
    [
        ('["user_abc"]', ["user_abc"]),
        ('["user_abc", "user_def"]', ["user_abc", "user_def"]),
        ("user_abc", ["user_abc"]),
        ("user_abc,user_def", ["user_abc", "user_def"]),
        ("user_abc, user_def", ["user_abc", "user_def"]),
        ("[user_abc]", ["user_abc"]),
        ("['user_abc']", ["user_abc"]),
        ('"user_abc"', ["user_abc"]),
        ("  user_abc  ", ["user_abc"]),
        ("", []),
        ("   ", []),
        ("[]", []),
    ],
)
def test_admin_ids_are_accepted_however_they_are_typed(monkeypatch, typed, expected) -> None:
    monkeypatch.setenv("ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS", typed)
    assert Settings().platform_admin_subjects == expected


def test_website_addresses_lose_a_trailing_slash(monkeypatch) -> None:
    monkeypatch.setenv("ROUTEBRIDGE_ALLOWED_ORIGINS", "https://routebridge-web.onrender.com/")
    assert Settings().allowed_origins == ["https://routebridge-web.onrender.com"]
    monkeypatch.setenv("ROUTEBRIDGE_ALLOWED_ORIGINS", '["https://a.example/", "https://b.example"]')
    assert Settings().allowed_origins == ["https://a.example", "https://b.example"]


def test_the_defaults_and_real_lists_still_work(monkeypatch) -> None:
    monkeypatch.delenv("ROUTEBRIDGE_PLATFORM_ADMIN_SUBJECTS", raising=False)
    monkeypatch.delenv("ROUTEBRIDGE_ALLOWED_ORIGINS", raising=False)
    settings = Settings()
    assert settings.platform_admin_subjects == [] and settings.allowed_origins == ["http://localhost:3000"]
    assert Settings(platform_admin_subjects=["user_x"], allowed_origins=["https://x.example"]).platform_admin_subjects == ["user_x"]
    assert as_text_list(None) == []
