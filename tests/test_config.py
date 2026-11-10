"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from whisprlink.config import Settings


def test_settings_load_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:local-test-token")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.telegram_bot_token.get_secret_value() == "123456:local-test-token"


def test_secret_is_not_exposed_in_settings_repr() -> None:
    token = "123456:local-test-token"
    settings = Settings(telegram_bot_token=token)

    assert token not in repr(settings)
    assert settings.telegram_bot_token.get_secret_value() == token


def test_blank_telegram_token_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(telegram_bot_token="   ")


def test_webhook_mode_is_rejected_until_implemented() -> None:
    with pytest.raises(ValidationError):
        Settings(
            telegram_bot_token="123456:local-test-token",
            bot_mode="webhook",
        )


def test_retention_days_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            telegram_bot_token="123456:local-test-token",
            data_retention_days=0,
        )


VALID_TOKEN = "123456789:AAH-valid_looking_token_value_1234567"
STRONG_SECRET = "x7Kq2mP9vL4nR8tW1zB6cD3fG5hJ0yUe"


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "telegram_bot_token": VALID_TOKEN,
        "deep_link_secret": STRONG_SECRET,
        "admin_telegram_ids": "111,222",
        "database_url": "postgresql+asyncpg://whisprlink:s3cure-Pass@db:5432/whisprlink",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_production_accepts_complete_configuration() -> None:
    settings = production_settings()

    assert settings.admin_telegram_ids == frozenset({111, 222})


@pytest.mark.parametrize(
    "overrides",
    [
        {"telegram_bot_token": "123456:local-test-token"},
        {"deep_link_secret": None},
        {"deep_link_secret": "short-secret"},
        {"deep_link_secret": "change-me-" + "a" * 40},
        {"deep_link_secret": VALID_TOKEN},
        {"admin_telegram_ids": ""},
        {"database_url": "postgresql+asyncpg://whisprlink:change-me@db:5432/whisprlink"},
    ],
    ids=[
        "token-format",
        "secret-missing",
        "secret-short",
        "secret-placeholder",
        "secret-equals-token",
        "no-admins",
        "placeholder-db-password",
    ],
)
def test_production_rejects_weak_or_missing_configuration(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        production_settings(**overrides)


def test_development_does_not_require_production_secrets() -> None:
    settings = Settings(telegram_bot_token="123456:local-test-token")

    assert settings.deep_link_secret is None
    assert settings.admin_telegram_ids == frozenset()


def test_admin_ids_are_parsed_from_comma_separated_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:local-test-token")
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", " 42, 7 ,")

    assert Settings().admin_telegram_ids == frozenset({42, 7})


@pytest.mark.parametrize("value", ["abc", "1,two", "0", "-5"])
def test_invalid_admin_ids_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(telegram_bot_token="123456:t", admin_telegram_ids=value)


@pytest.mark.parametrize(
    "url", ["postgresql://u:p@h/db", "sqlite+aiosqlite:///x.db", "mysql://u:p@h/db"]
)
def test_database_url_must_use_asyncpg_driver(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(telegram_bot_token="123456:t", database_url=url)


@pytest.mark.parametrize("url", ["http://localhost", "localhost:6379", "unix:///tmp/redis.sock"])
def test_redis_url_scheme_is_validated(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(telegram_bot_token="123456:t", redis_url=url)


def test_infrastructure_settings_need_no_telegram_token() -> None:
    from whisprlink.config import InfrastructureSettings

    settings = InfrastructureSettings()

    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_pool_limits_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(telegram_bot_token="123456:t", db_pool_size=0)
