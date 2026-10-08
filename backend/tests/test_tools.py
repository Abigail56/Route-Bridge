import os
import subprocess
import sys

import pytest
from pathlib import Path

from sqlalchemy import create_engine, text

from routebridge.tools.gen_secrets import generate

API_DIR = Path(__file__).resolve().parents[1] / "apps" / "api"


def test_generated_secrets_pass_the_production_length_checks_and_are_unique() -> None:
    first, second = generate(), generate()
    for name, value in first.items():
        assert len(value) >= 32, name
    assert first != second  # never deterministic


def test_migrate_tool_brings_an_empty_database_to_head_and_is_idempotent(tmp_path) -> None:
    db = tmp_path / "migrate.db"
    env = {**os.environ, "ROUTEBRIDGE_DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONPATH": str(API_DIR / "src")}
    for _ in range(2):  # the second run must be a no-op, not an error
        result = subprocess.run([sys.executable, "-m", "routebridge.tools.migrate"], cwd=API_DIR, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "c9d0e1f2a3b4"
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"order", "trackingtoken", "stopcorrection", "deliveryotp", "notificationdelivery"} <= tables
    engine.dispose()


def test_send_test_sms_tool_never_sends_in_log_mode_and_hides_the_key(capsys) -> None:
    from routebridge.tools.send_test_sms import main

    assert main(["+2348012345678"]) == 0
    out = capsys.readouterr().out
    assert "sends nothing" in out and "2348012" not in out  # number is masked in the output
    assert main([]) == 2


def test_migrate_waits_for_a_database_that_is_still_starting() -> None:
    from sqlalchemy.exc import OperationalError

    from routebridge.tools.migrate import wait_for_database

    class Engine:
        def __init__(self, failures: int) -> None:
            self.failures, self.calls = failures, 0

        def connect(self):
            self.calls += 1
            if self.calls <= self.failures:
                raise OperationalError("SELECT 1", {}, Exception("connection refused"))

            class Connection:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, *args):
                    return False

                def execute(self_inner, *args):
                    return None

            return Connection()

    naps: list[float] = []
    engine = Engine(failures=3)
    wait_for_database(engine, timeout=60, interval=2, sleep=naps.append)
    assert engine.calls == 4 and naps == [2, 2, 2]  # refused three times, then it connected

    ticks = iter(range(0, 1000, 10))  # a fake clock that jumps 10 seconds per look
    with pytest.raises(OperationalError):
        wait_for_database(Engine(failures=99), timeout=30, interval=2, sleep=lambda _: None, clock=lambda: next(ticks))
