import os
import subprocess
import sys
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
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "c3d4e5f6a7b8"
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"order", "trackingtoken", "stopcorrection", "deliveryotp", "notificationdelivery"} <= tables
    engine.dispose()


def test_send_test_sms_tool_never_sends_in_log_mode_and_hides_the_key(capsys) -> None:
    from routebridge.tools.send_test_sms import main

    assert main(["+2348012345678"]) == 0
    out = capsys.readouterr().out
    assert "sends nothing" in out and "2348012" not in out  # number is masked in the output
    assert main([]) == 2
