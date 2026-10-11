"""The one-command start used by hosting platforms: migrate first, then serve on the platform's port."""
import pytest

from routebridge.tools import serve


def test_it_migrates_then_serves_on_the_platform_port(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(serve, "migrate", lambda: calls.append("migrate"))
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: calls.append(("run", app, kwargs)))
    monkeypatch.setenv("PORT", "10000")
    serve.main()
    assert calls == ["migrate", ("run", "routebridge.main:app", {"host": "0.0.0.0", "port": 10000})]


def test_it_uses_port_8000_when_none_is_given(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(serve, "migrate", lambda: None)
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    monkeypatch.delenv("PORT", raising=False)
    serve.main()
    assert calls == [{"host": "0.0.0.0", "port": 8000}]


def test_a_failed_migration_stops_everything_and_the_server_never_starts(monkeypatch) -> None:
    started: list = []

    def broken() -> None:
        raise RuntimeError("database is down")

    monkeypatch.setattr(serve, "migrate", broken)
    monkeypatch.setattr(serve.uvicorn, "run", lambda *a, **k: started.append(True))
    with pytest.raises(SystemExit) as exit_info:
        serve.main()
    assert exit_info.value.code == 1 and started == []
