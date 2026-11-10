"""Async PostgreSQL engine lifecycle and transaction helpers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from whisprlink.config import InfrastructureSettings
from whisprlink.infrastructure.readiness import wait_until_ready
from whisprlink.logging_config import get_logger

logger = get_logger(__name__)


class Database:
    """Owns the async engine and hands out sessions.

    Transactions are expected to be short. ``idle_in_transaction_session_timeout`` makes
    PostgreSQL terminate sessions that sit in a transaction (for example while awaiting a
    Telegram request), so row locks cannot be held indefinitely.
    """

    def __init__(self, settings: InfrastructureSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_recycle=settings.db_pool_recycle_seconds,
            pool_pre_ping=True,
            connect_args={
                "timeout": settings.db_connect_timeout_seconds,
                "command_timeout": settings.db_command_timeout_seconds,
                "server_settings": {
                    "application_name": "whisprlink",
                    "timezone": "UTC",
                    "idle_in_transaction_session_timeout": str(
                        settings.db_idle_in_transaction_timeout_seconds * 1000
                    ),
                },
            },
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session without an implicit transaction; the caller controls commit."""
        async with self._session_factory() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Yield a session inside one transaction: commit on success, roll back on error."""
        async with self._session_factory() as session, session.begin():
            yield session

    async def ping(self) -> None:
        """Raise if PostgreSQL cannot execute a trivial query."""
        async with self._engine.connect() as connection:
            await connection.execute(sa.text("SELECT 1"))

    async def wait_until_ready(self) -> None:
        await wait_until_ready(
            self.ping,
            name="postgresql",
            attempts=self._settings.startup_retry_attempts,
            delay_seconds=self._settings.startup_retry_delay_seconds,
        )

    async def dispose(self) -> None:
        """Close all pooled connections."""
        await self._engine.dispose()
        logger.info("database_disposed")
