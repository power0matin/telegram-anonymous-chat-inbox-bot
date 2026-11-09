"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Secrets are represented as SecretStr so their values are not exposed in repr output.
    The bot currently supports long polling only; webhook mode is intentionally rejected
    until its HTTP ingress and secret validation are implemented.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    bot_mode: Literal["polling"] = "polling"

    telegram_bot_token: SecretStr
    telegram_bot_username: str | None = None

    database_url: str = "postgresql+asyncpg://whisprlink:change-me@localhost:5432/whisprlink"
    redis_url: str = "redis://localhost:6379/0"

    deep_link_secret: SecretStr | None = None
    webhook_secret_token: SecretStr | None = None
    webhook_base_url: str | None = None

    # Reserved for future retention logic; no deletion job exists yet.
    data_retention_days: int = Field(default=30, gt=0)

    @field_validator("telegram_bot_token")
    @classmethod
    def validate_telegram_bot_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("TELEGRAM_BOT_TOKEN must not be empty")
        return value

    @field_validator("telegram_bot_username")
    @classmethod
    def normalize_bot_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().removeprefix("@")
        return normalized or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
