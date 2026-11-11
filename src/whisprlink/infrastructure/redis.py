"""Redis client lifecycle.

Redis holds ephemeral coordination data only; it is never the source of truth. The client
reconnects automatically, so a temporary Redis outage surfaces as per-call errors rather than
a permanently broken process.
"""

from redis.asyncio import BlockingConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from whisprlink.config import InfrastructureSettings
from whisprlink.infrastructure.readiness import wait_until_ready
from whisprlink.logging_config import get_logger

logger = get_logger(__name__)


class RedisManager:
    """Owns the Redis connection pool."""

    def __init__(self, settings: InfrastructureSettings) -> None:
        self._settings = settings
        # A blocking pool makes callers wait (bounded) for a free connection under bursts
        # instead of failing immediately with "Too many connections".
        pool = BlockingConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            timeout=settings.redis_pool_timeout_seconds,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
            health_check_interval=settings.redis_health_check_interval_seconds,
            retry=Retry(ExponentialBackoff(cap=2.0, base=0.1), settings.redis_retry_attempts),
            retry_on_error=[RedisConnectionError, RedisTimeoutError],
        )
        self._client: Redis = Redis(connection_pool=pool)

    @property
    def client(self) -> Redis:
        return self._client

    async def ping(self) -> None:
        """Raise if Redis does not answer PING."""
        if not await self._client.ping():
            raise RedisConnectionError("Redis PING returned a falsy response")

    async def wait_until_ready(self) -> None:
        await wait_until_ready(
            self.ping,
            name="redis",
            attempts=self._settings.startup_retry_attempts,
            delay_seconds=self._settings.startup_retry_delay_seconds,
        )

    async def close(self) -> None:
        """Close the pool and release connections."""
        await self._client.aclose(close_connection_pool=True)
        logger.info("redis_closed")
