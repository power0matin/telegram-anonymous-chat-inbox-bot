"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from whisprlink.config import Settings


def test_settings_load_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:local-test-token")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.telegram_bot_token.get_secret_value() == "123456:local-test-token"


def test_secret_is_not_exposed_in_settings_repr() -> None:
    token = "123456:local-test-token"
    settings = Settings(_env_file=None, telegram_bot_token=token)

    assert token not in repr(settings)
    assert settings.telegram_bot_token.get_secret_value() == token


def test_blank_telegram_token_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_bot_token="   ")


def test_webhook_mode_is_rejected_until_implemented() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            telegram_bot_token="123456:local-test-token",
            bot_mode="webhook",
        )


def test_retention_days_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            telegram_bot_token="123456:local-test-token",
            data_retention_days=0,
        )
