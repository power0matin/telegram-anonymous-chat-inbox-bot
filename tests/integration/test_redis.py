"""Redis lifecycle, expiry, and outage-recovery tests."""

import asyncio
from urllib.parse import urlparse

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from tests.conftest import infrastructure_settings
from tests.tcp_proxy import TcpProxy
from whisprlink.infrastructure.readiness import DependencyUnavailableError
from whisprlink.infrastructure.redis import RedisManager

pytestmark = pytest.mark.integration


async def test_ping_and_basic_roundtrip(redis_manager: RedisManager, redis_prefix: str) -> None:
    await redis_manager.ping()
    client = redis_manager.client

    await client.set(f"{redis_prefix}key", "value")

    assert await client.get(f"{redis_prefix}key") == "value"
    await client.delete(f"{redis_prefix}key")


async def test_keys_expire(redis_manager: RedisManager, redis_prefix: str) -> None:
    client = redis_manager.client

    await client.set(f"{redis_prefix}short", "1", px=100)
    assert await client.get(f"{redis_prefix}short") == "1"
    await asyncio.sleep(0.25)

    assert await client.get(f"{redis_prefix}short") is None


async def test_set_if_absent_provides_short_lived_coordination(
    redis_manager: RedisManager, redis_prefix: str
) -> None:
    client = redis_manager.client
    key = f"{redis_prefix}lock"

    results = await asyncio.gather(*(client.set(key, str(n), nx=True, px=2000) for n in range(25)))

    assert sum(1 for result in results if result) == 1
    await client.delete(key)


async def test_wait_until_ready_gives_up_on_an_unreachable_server() -> None:
    manager = RedisManager(
        infrastructure_settings("postgresql+asyncpg://u:p@h/d", "redis://127.0.0.1:1/0")
    )
    try:
        with pytest.raises(DependencyUnavailableError, match="redis not ready after 2"):
            await manager.wait_until_ready()
    finally:
        await manager.close()


async def test_client_recovers_after_a_redis_outage(redis_test_url: str, redis_prefix: str) -> None:
    parsed = urlparse(redis_test_url)
    proxy = TcpProxy(parsed.hostname or "127.0.0.1", parsed.port or 6379)
    await proxy.start()
    manager = RedisManager(
        infrastructure_settings(
            "postgresql+asyncpg://u:p@h/d",
            f"redis://127.0.0.1:{proxy.port}{parsed.path or '/0'}",
            redis_socket_timeout_seconds=1.0,
            redis_retry_attempts=1,
        )
    )
    try:
        await manager.ping()
        await manager.client.set(f"{redis_prefix}k", "before")

        await proxy.stop()  # outage
        with pytest.raises(RedisConnectionError):
            await manager.ping()

        await proxy.start(port=proxy.port)  # recovery on the same address
        await manager.ping()
        assert await manager.client.get(f"{redis_prefix}k") == "before"
        await manager.client.delete(f"{redis_prefix}k")
    finally:
        await manager.close()
        await proxy.stop()
