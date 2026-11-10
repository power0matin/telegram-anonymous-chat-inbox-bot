"""Alembic migration tests against a disposable PostgreSQL database."""

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import alembic_config
from tests.test_models import AGREED_TABLES

pytestmark = pytest.mark.integration


async def _scalar_list(url: str, query: str) -> list[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return [row[0] for row in await connection.execute(sa.text(query))]
    finally:
        await engine.dispose()


async def _tables(url: str) -> set[str]:
    return set(
        await _scalar_list(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )


async def test_upgrade_from_empty_database_creates_every_table(empty_database_url: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(empty_database_url), "head")

    assert await _tables(empty_database_url) == AGREED_TABLES | {"alembic_version"}


async def test_models_and_migrations_have_no_drift(empty_database_url: str) -> None:
    config = alembic_config(empty_database_url)
    await asyncio.to_thread(command.upgrade, config, "head")

    # Raises CommandError when autogenerate would produce any operation.
    await asyncio.to_thread(command.check, config)


async def test_downgrade_to_base_removes_tables_and_functions_then_upgrades_again(
    empty_database_url: str,
) -> None:
    config = alembic_config(empty_database_url)
    await asyncio.to_thread(command.upgrade, config, "head")

    await asyncio.to_thread(command.downgrade, config, "base")

    assert await _tables(empty_database_url) == {"alembic_version"}
    assert (
        await _scalar_list(
            empty_database_url, "SELECT proname FROM pg_proc WHERE proname LIKE 'whisprlink_%'"
        )
        == []
    )

    await asyncio.to_thread(command.upgrade, config, "head")
    assert await _tables(empty_database_url) == AGREED_TABLES | {"alembic_version"}


async def test_upgrade_is_idempotent_at_head(empty_database_url: str) -> None:
    config = alembic_config(empty_database_url)

    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.upgrade, config, "head")

    assert await _scalar_list(empty_database_url, "SELECT version_num FROM alembic_version") == [
        "0001"
    ]


def test_migration_history_is_linear_with_a_single_head(empty_database_url: str) -> None:
    script = ScriptDirectory.from_config(alembic_config(empty_database_url))

    assert script.get_heads() == ["0001"]
    assert [revision.revision for revision in script.walk_revisions()] == ["0001"]


async def test_integrity_triggers_are_installed(empty_database_url: str) -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(empty_database_url), "head")

    triggers = await _scalar_list(
        empty_database_url,
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal ORDER BY tgname",
    )

    assert triggers == [
        "trg_admin_audit_logs_append_only",
        "trg_inbox_messages_guard_insert",
        "trg_inbox_open_events_guard_insert",
        "trg_inbox_threads_guard_insert",
        "trg_random_chat_participants_guard_insert",
        "trg_random_chat_sessions_release_participants",
    ]


async def test_offline_sql_generation_works(empty_database_url: str) -> None:
    config = alembic_config(empty_database_url)

    # --sql mode renders DDL without connecting; it must succeed for DBAs reviewing the change.
    await asyncio.to_thread(command.upgrade, config, "head", sql=True)
