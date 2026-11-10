"""Typed application settings loaded from environment variables."""

import re
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_TOKEN_PATTERN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "replace-me", "example")
_MIN_PRODUCTION_SECRET_LENGTH = 32


class InfrastructureSettings(BaseSettings):
    """Settings required to reach PostgreSQL and Redis.

    Split from :class:`Settings` so tooling such as Alembic and the health check can run
    without a Telegram token.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    database_url: str = "postgresql+asyncpg://whisprlink:change-me@localhost:5432/whisprlink"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_timeout_seconds: float = Field(default=10.0, gt=0)
    db_pool_recycle_seconds: int = Field(default=1800, gt=0)
    db_connect_timeout_seconds: float = Field(default=10.0, gt=0)
    db_command_timeout_seconds: float = Field(default=30.0, gt=0)
    db_idle_in_transaction_timeout_seconds: int = Field(default=30, gt=0)

    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = Field(default=20, ge=1, le=200)
    redis_pool_timeout_seconds: float = Field(default=5.0, gt=0)
    redis_socket_timeout_seconds: float = Field(default=5.0, gt=0)
    redis_health_check_interval_seconds: int = Field(default=30, gt=0)
    redis_retry_attempts: int = Field(default=3, ge=0, le=10)

    startup_retry_attempts: int = Field(default=10, ge=1, le=120)
    startup_retry_delay_seconds: float = Field(default=2.0, gt=0)
    health_check_timeout_seconds: float = Field(default=5.0, gt=0)

    heartbeat_path: str = "/tmp/whisprlink.heartbeat"
    heartbeat_interval_seconds: float = Field(default=15.0, gt=0)
    heartbeat_max_age_seconds: float = Field(default=60.0, gt=0)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must use the redis:// or rediss:// scheme")
        return value

    @model_validator(mode="after")
    def reject_placeholder_database_password_in_production(self) -> "InfrastructureSettings":
        if self.app_env == "production" and _looks_like_placeholder(self.database_url):
            raise ValueError("DATABASE_URL contains a placeholder credential in production")
        return self


class Settings(InfrastructureSettings):
    """Runtime configuration.

    Secrets are represented as SecretStr so their values are not exposed in repr output.
    The bot supports long polling only; webhook mode is rejected until its HTTP ingress and
    secret validation are implemented.
    """

    bot_mode: Literal["polling"] = "polling"

    telegram_bot_token: SecretStr
    telegram_bot_username: str | None = None

    admin_telegram_ids: Annotated[frozenset[int], NoDecode] = frozenset()
    deep_link_secret: SecretStr | None = None

    # Reserved: no retention job exists yet; Phase 6 replaces this with per-category periods.
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

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> object:
        if value is None or value == "":
            return frozenset()
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            try:
                return frozenset(int(part) for part in parts)
            except ValueError as exc:
                raise ValueError("ADMIN_TELEGRAM_IDS must be comma-separated integers") from exc
        return value

    @field_validator("admin_telegram_ids")
    @classmethod
    def validate_admin_ids(cls, value: frozenset[int]) -> frozenset[int]:
        if any(item <= 0 for item in value):
            raise ValueError("ADMIN_TELEGRAM_IDS must contain positive Telegram user IDs")
        return value

    @model_validator(mode="after")
    def enforce_production_requirements(self) -> "Settings":
        if self.app_env != "production":
            return self

        token = self.telegram_bot_token.get_secret_value()
        if not _TOKEN_PATTERN.match(token):
            raise ValueError("TELEGRAM_BOT_TOKEN does not look like a real BotFather token")

        if self.deep_link_secret is None:
            raise ValueError("DEEP_LINK_SECRET is required in production")
        secret = self.deep_link_secret.get_secret_value()
        if len(secret) < _MIN_PRODUCTION_SECRET_LENGTH or _looks_like_placeholder(secret):
            raise ValueError(
                f"DEEP_LINK_SECRET must be a non-placeholder value of at least "
                f"{_MIN_PRODUCTION_SECRET_LENGTH} characters in production"
            )
        if secret == token:
            raise ValueError("DEEP_LINK_SECRET must differ from TELEGRAM_BOT_TOKEN")

        if not self.admin_telegram_ids:
            raise ValueError("ADMIN_TELEGRAM_IDS must name at least one admin in production")
        return self


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


@lru_cache(maxsize=1)
def get_infrastructure_settings() -> InfrastructureSettings:
    """Return infrastructure-only settings for tooling that needs no Telegram token."""
    return InfrastructureSettings()
