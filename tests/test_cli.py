"""Command-line behaviour that needs no external services."""

import time
from pathlib import Path

import pytest

from whisprlink.app import healthcheck, main
from whisprlink.config import InfrastructureSettings


def test_invalid_configuration_exits_with_code_2_without_echoing_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from whisprlink.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:short")
    monkeypatch.setenv("DEEP_LINK_SECRET", "super-secret-value-that-must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:leaky-password@h/db")

    with pytest.raises(SystemExit) as exit_info:
        main(["run"])

    assert exit_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Invalid configuration" in stderr
    for secret in ("super-secret-value", "leaky-password", "123456:short"):
        assert secret not in stderr
    get_settings.cache_clear()


def test_missing_token_is_reported_by_name(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from whisprlink.config import get_settings

    get_settings.cache_clear()
    monkeypatch.chdir("/")

    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err
    get_settings.cache_clear()


async def test_liveness_healthcheck_reflects_heartbeat_freshness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    beat = tmp_path / "beat"
    settings = InfrastructureSettings(heartbeat_path=str(beat))

    assert await healthcheck(settings, liveness_only=True) == 1

    beat.write_text(str(time.time()))
    assert await healthcheck(settings, liveness_only=True) == 0
    assert '"liveness": true' in capsys.readouterr().out
