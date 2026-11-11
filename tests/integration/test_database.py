"""Async engine lifecycle tests."""

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from tests.conftest import infrastructure_settings
from whisprlink.infrastructure.readiness import DependencyUnavailableError
from whisprlink.persistence.database import Database

pytestmark = pytest.mark.integration


async def test_ping_succeeds_against_a_live_server(database: Database) -> None:
    await database.ping()


async def test_connections_use_utc_application_name_and_idle_transaction_guard(
    database: Database,
) -> None:
    async with database.session() as session:
        values = {
            name: (await session.execute(sa.text(f"SHOW {name}"))).scalar_one()
            for name in ("timezone", "application_name", "idle_in_transaction_session_timeout")
        }

    assert values == {
        "timezone": "UTC",
        "application_name": "whisprlink",
        "idle_in_transaction_session_timeout": "30s",
    }


async def test_session_starts_without_an_implicit_transaction(database: Database) -> None:
    async with database.session() as session:
        assert not session.in_transaction()


async def test_transaction_commits_on_success(database: Database) -> None:
    async with database.transaction() as session:
        await session.execute(sa.text("INSERT INTO users (telegram_user_id) VALUES (1)"))

    async with database.session() as session:
        count = (await session.execute(sa.text("SELECT count(*) FROM users"))).scalar_one()
    assert count == 1


async def test_transaction_rolls_back_on_error(database: Database) -> None:
    with pytest.raises(RuntimeError, match="abort"):
        async with database.transaction() as session:
            await session.execute(sa.text("INSERT INTO users (telegram_user_id) VALUES (2)"))
            raise RuntimeError("abort")

    async with database.session() as session:
        count = (await session.execute(sa.text("SELECT count(*) FROM users"))).scalar_one()
    assert count == 0


async def test_pool_recovers_after_the_server_kills_a_connection(database: Database) -> None:
    async with database.engine.connect() as victim, database.engine.connect() as killer:
        pid = (await victim.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()
        await victim.rollback()
        await killer.execute(sa.text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        await killer.commit()

    await database.ping()  # pool_pre_ping discards the dead connection transparently


async def test_idle_in_transaction_sessions_are_terminated_by_the_server(
    migrated_database_url: str, redis_test_url: str
) -> None:
    short = Database(
        infrastructure_settings(
            migrated_database_url, redis_test_url, db_idle_in_transaction_timeout_seconds=1
        )
    )
    try:
        with pytest.raises(DBAPIError):
            async with short.transaction() as session:
                await session.execute(sa.text("SELECT 1"))
                await asyncio.sleep(2.0)  # stands in for a Telegram call held inside a transaction
                await session.execute(sa.text("SELECT 1"))
    finally:
        await short.dispose()


async def test_pool_is_bounded(migrated_database_url: str, redis_test_url: str) -> None:
    small = Database(
        infrastructure_settings(
            migrated_database_url,
            redis_test_url,
            db_pool_size=1,
            db_max_overflow=0,
            db_pool_timeout_seconds=0.2,
        )
    )
    try:
        async with small.session() as first:
            await first.execute(sa.text("SELECT 1"))
            with pytest.raises(PoolTimeoutError):
                async with small.session() as second:
                    await second.execute(sa.text("SELECT 1"))
    finally:
        await small.dispose()


async def test_wait_until_ready_gives_up_on_an_unreachable_server() -> None:
    unreachable = Database(
        infrastructure_settings(
            "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none",
            db_connect_timeout_seconds=0.5,
        )
    )
    try:
        with pytest.raises(DependencyUnavailableError, match="postgresql not ready after 2"):
            await unreachable.wait_until_ready()
    finally:
        await unreachable.dispose()
