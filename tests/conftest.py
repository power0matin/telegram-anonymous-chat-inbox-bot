"""Shared fixtures.

Integration tests need a disposable PostgreSQL server and Redis. Point them at one with:

    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/postgres   (server admin URL)
    TEST_REDIS_URL=redis://host:port/15

Every test session creates its own uniquely named database and drops it afterwards; Redis
tests use a unique key prefix. When the variables are unset the integration tests are
skipped, unless ``REQUIRE_INTEGRATION=1`` is set (as in CI), in which case they fail.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from whisprlink.config import InfrastructureSettings
from whisprlink.infrastructure.redis import RedisManager
from whisprlink.persistence.database import Database

ROOT = Path(__file__).resolve().parent.parent
REQUIRE_INTEGRATION = os.environ.get("REQUIRE_INTEGRATION") == "1"


def _integration_env(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    message = f"{name} is not set; integration tests need disposable PostgreSQL and Redis"
    if REQUIRE_INTEGRATION:
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


async def create_database(admin_url: str) -> str:
    """Create an empty uniquely named database and return its URL."""
    name = f"whisprlink_test_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()
    return make_url(admin_url).set(database=name).render_as_string(hide_password=False)


async def drop_database(admin_url: str, database_url: str) -> None:
    name = make_url(database_url).database
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await engine.dispose()


@pytest.fixture(scope="session")
def admin_database_url() -> str:
    return _integration_env("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def redis_test_url() -> str:
    return _integration_env("TEST_REDIS_URL")


@pytest_asyncio.fixture(scope="session")
async def migrated_database_url(admin_database_url: str) -> AsyncIterator[str]:
    """A disposable database upgraded to ``head`` through the real Alembic migrations."""
    url = await create_database(admin_database_url)
    await asyncio.to_thread(command.upgrade, alembic_config(url), "head")
    yield url
    await drop_database(admin_database_url, url)


@pytest_asyncio.fixture
async def empty_database_url(admin_database_url: str) -> AsyncIterator[str]:
    url = await create_database(admin_database_url)
    yield url
    await drop_database(admin_database_url, url)


def infrastructure_settings(
    database_url: str, redis_url: str = "redis://localhost:6379/0", **overrides: object
) -> InfrastructureSettings:
    return InfrastructureSettings(
        app_env="test",
        database_url=database_url,
        redis_url=redis_url,
        startup_retry_attempts=2,
        startup_retry_delay_seconds=0.05,
        **overrides,  # type: ignore[arg-type]
    )


@pytest_asyncio.fixture
async def database(migrated_database_url: str, redis_test_url: str) -> AsyncIterator[Database]:
    """Database handle on a migrated schema with every table emptied before the test."""
    db = Database(infrastructure_settings(migrated_database_url, redis_test_url))
    async with db.engine.begin() as connection:
        tables = (
            await connection.execute(
                sa.text(
                    "SELECT string_agg(format('%I', tablename), ', ') FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
        ).scalar_one()
        await connection.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield db
    await db.dispose()


@pytest_asyncio.fixture
async def redis_manager(
    migrated_database_url: str, redis_test_url: str
) -> AsyncIterator[RedisManager]:
    manager = RedisManager(infrastructure_settings(migrated_database_url, redis_test_url))
    yield manager
    await manager.close()


@pytest.fixture
def redis_prefix() -> str:
    return f"whisprlink-test:{uuid.uuid4().hex}:"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep ambient configuration (environment variables and any .env file) out of tests."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith(
            ("TELEGRAM_", "DATABASE_", "REDIS_", "DEEP_LINK_", "ADMIN_")
        ) or name in {
            "APP_ENV",
            "LOG_LEVEL",
            "LOG_FORMAT",
            "BOT_MODE",
        }:
            monkeypatch.delenv(name)
    yield
