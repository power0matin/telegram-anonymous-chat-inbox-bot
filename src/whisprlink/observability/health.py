"""Readiness (dependency) and liveness (event-loop heartbeat) checks."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from whisprlink.logging_config import get_logger

logger = get_logger(__name__)


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    name: str
    healthy: bool
    latency_ms: float
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    """PostgreSQL is authoritative (required); Redis is ephemeral (degrades, not fails)."""

    database: ComponentHealth
    redis: ComponentHealth

    @property
    def status(self) -> HealthStatus:
        if not self.database.healthy:
            return HealthStatus.UNAVAILABLE
        if not self.redis.healthy:
            return HealthStatus.DEGRADED
        return HealthStatus.OK

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "components": {
                component.name: {
                    "healthy": component.healthy,
                    "latency_ms": round(component.latency_ms, 1),
                    "error_type": component.error_type,
                }
                for component in (self.database, self.redis)
            },
        }


async def check_component(
    name: str, probe: Callable[[], Awaitable[None]], *, timeout_seconds: float
) -> ComponentHealth:
    """Run one probe with a timeout; never raises."""
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe(), timeout=timeout_seconds)
    except Exception as exc:
        return ComponentHealth(
            name=name,
            healthy=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_type=type(exc).__name__,
        )
    return ComponentHealth(
        name=name, healthy=True, latency_ms=(time.perf_counter() - started) * 1000
    )


async def check_readiness(
    database_ping: Callable[[], Awaitable[None]],
    redis_ping: Callable[[], Awaitable[None]],
    *,
    timeout_seconds: float,
) -> HealthReport:
    database, redis = await asyncio.gather(
        check_component("database", database_ping, timeout_seconds=timeout_seconds),
        check_component("redis", redis_ping, timeout_seconds=timeout_seconds),
    )
    return HealthReport(database=database, redis=redis)


class Heartbeat:
    """Periodically touches a file so an external probe can tell the event loop is alive."""

    def __init__(self, path: str, interval_seconds: float) -> None:
        self._path = Path(path)
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def beat(self) -> None:
        self._path.write_text(str(time.time()), encoding="utf-8")

    async def _run(self) -> None:
        while True:
            try:
                self.beat()
            except OSError as exc:
                logger.error("heartbeat_write_failed", error_type=type(exc).__name__)
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="heartbeat")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._path.unlink(missing_ok=True)


def check_liveness(path: str, *, max_age_seconds: float) -> bool:
    """True when the heartbeat file exists and is fresh."""
    try:
        last_beat = float(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (time.time() - last_beat) <= max_age_seconds
