"""Application startup, signal handling, and graceful shutdown with real dependencies."""

import asyncio
import os
import signal
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import DeleteWebhook, GetMe, GetUpdates, TelegramMethod
from aiogram.types import User

from whisprlink.app import Application, _install_signal_handlers
from whisprlink.config import Settings
from whisprlink.infrastructure.readiness import DependencyUnavailableError

pytestmark = pytest.mark.integration

TOKEN = "123456789:AAH-valid_looking_token_value_1234567"


class FakeTelegramSession(BaseSession):
    """Answers the few Bot API calls polling makes, with no network access."""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False
        self.get_updates_calls = 0

    async def close(self) -> None:
        self.closed = True

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 - mirrors aiogram's signature
    ) -> Any:
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="WhisprLink", username="test_bot")
        if isinstance(method, DeleteWebhook):
            return True
        if isinstance(method, GetUpdates):
            self.get_updates_calls += 1
            await asyncio.sleep(0.05)
            return []
        raise AssertionError(f"unexpected Bot API call: {type(method).__name__}")

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""


def make_application(
    database_url: str, redis_url: str, heartbeat: Path, **overrides: Any
) -> tuple[Application, FakeTelegramSession]:
    session = FakeTelegramSession()
    settings = Settings(
        app_env="test",
        telegram_bot_token=TOKEN,
        database_url=database_url,
        redis_url=redis_url,
        heartbeat_path=str(heartbeat),
        heartbeat_interval_seconds=0.05,
        startup_retry_attempts=2,
        startup_retry_delay_seconds=0.05,
        **overrides,
    )
    return Application(settings, bot=Bot(TOKEN, session=session)), session


async def wait_for(predicate: Any, limit_seconds: float = 5.0) -> None:
    async with asyncio.timeout(limit_seconds):
        while not predicate():  # noqa: ASYNC110 - polls files/counters, not an event
            await asyncio.sleep(0.02)


async def test_request_stop_shuts_down_cleanly_and_releases_everything(
    migrated_database_url: str, redis_test_url: str, tmp_path: Path
) -> None:
    beat = tmp_path / "heartbeat"
    application, session = make_application(migrated_database_url, redis_test_url, beat)

    running = asyncio.create_task(application.run())
    await wait_for(lambda: beat.exists() and session.get_updates_calls > 0)

    application.request_stop()
    await asyncio.wait_for(running, timeout=10)

    assert session.closed
    assert not beat.exists(), "heartbeat file must be removed on shutdown"
    assert application._closed


async def test_sigterm_triggers_graceful_shutdown(
    migrated_database_url: str, redis_test_url: str, tmp_path: Path
) -> None:
    beat = tmp_path / "heartbeat"
    application, session = make_application(migrated_database_url, redis_test_url, beat)
    _install_signal_handlers(application)

    running = asyncio.create_task(application.run())
    await wait_for(lambda: session.get_updates_calls > 0)

    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(running, timeout=10)

    assert session.closed
    assert not beat.exists()


async def test_startup_fails_fast_when_postgresql_is_unreachable_and_still_cleans_up(
    redis_test_url: str, tmp_path: Path
) -> None:
    beat = tmp_path / "heartbeat"
    application, session = make_application(
        "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none",
        redis_test_url,
        beat,
        db_connect_timeout_seconds=0.5,
    )

    with pytest.raises(DependencyUnavailableError, match="postgresql"):
        await application.run()

    assert session.closed
    assert not beat.exists()


async def test_startup_fails_fast_when_redis_is_unreachable(
    migrated_database_url: str, tmp_path: Path
) -> None:
    application, session = make_application(
        migrated_database_url,
        "redis://127.0.0.1:1/0",
        tmp_path / "heartbeat",
        redis_retry_attempts=0,
    )

    with pytest.raises(DependencyUnavailableError, match="redis"):
        await application.run()

    assert session.closed


async def test_shutdown_is_idempotent(
    migrated_database_url: str, redis_test_url: str, tmp_path: Path
) -> None:
    application, _ = make_application(migrated_database_url, redis_test_url, tmp_path / "beat")

    await application.shutdown()
    await application.shutdown()


async def test_handlers_receive_infrastructure_through_workflow_data(
    migrated_database_url: str, redis_test_url: str, tmp_path: Path
) -> None:
    application, _ = make_application(migrated_database_url, redis_test_url, tmp_path / "beat")

    data = application.dispatcher.workflow_data
    try:
        assert data["database"] is application.database
        assert data["redis"] is application.redis
        assert data["settings"] is application.settings
    finally:
        await application.shutdown()
