"""Health report and heartbeat tests (no external services)."""

import asyncio
import os
import time
from pathlib import Path

import pytest

from whisprlink.observability.health import (
    ComponentHealth,
    HealthReport,
    HealthStatus,
    Heartbeat,
    check_component,
    check_liveness,
    check_readiness,
)


def component(name: str, healthy: bool) -> ComponentHealth:
    return ComponentHealth(name=name, healthy=healthy, latency_ms=1.0)


@pytest.mark.parametrize(
    ("database_ok", "redis_ok", "expected"),
    [
        (True, True, HealthStatus.OK),
        (True, False, HealthStatus.DEGRADED),
        (False, True, HealthStatus.UNAVAILABLE),
        (False, False, HealthStatus.UNAVAILABLE),
    ],
)
def test_report_status_treats_postgresql_as_required_and_redis_as_optional(
    database_ok: bool, redis_ok: bool, expected: HealthStatus
) -> None:
    report = HealthReport(
        database=component("database", database_ok), redis=component("redis", redis_ok)
    )

    assert report.status is expected
    assert report.as_dict()["status"] == expected.value


async def test_probe_exception_is_reported_not_raised() -> None:
    async def failing() -> None:
        raise ConnectionError("boom")

    result = await check_component("x", failing, timeout_seconds=1)

    assert result.healthy is False
    assert result.error_type == "ConnectionError"


async def test_probe_timeout_is_reported_as_unhealthy() -> None:
    async def hanging() -> None:
        await asyncio.sleep(10)

    result = await check_component("x", hanging, timeout_seconds=0.05)

    assert result.healthy is False
    assert result.error_type == "TimeoutError"


async def test_readiness_runs_both_probes() -> None:
    async def ok() -> None:
        return None

    async def down() -> None:
        raise OSError

    report = await check_readiness(ok, down, timeout_seconds=1)

    assert report.status is HealthStatus.DEGRADED


def test_liveness_requires_a_fresh_heartbeat_file(tmp_path: Path) -> None:
    path = tmp_path / "beat"

    assert check_liveness(str(path), max_age_seconds=60) is False

    path.write_text(str(time.time()))
    assert check_liveness(str(path), max_age_seconds=60) is True

    path.write_text(str(time.time() - 120))
    assert check_liveness(str(path), max_age_seconds=60) is False

    path.write_text("not-a-number")
    assert check_liveness(str(path), max_age_seconds=60) is False


async def test_heartbeat_writes_repeatedly_and_cleans_up(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    heartbeat = Heartbeat(str(path), interval_seconds=0.02)

    heartbeat.start()
    await asyncio.sleep(0.01)
    first = path.read_text()
    await asyncio.sleep(0.1)
    second = path.read_text()
    await heartbeat.stop()

    assert float(second) > float(first)
    assert not path.exists()


async def test_heartbeat_survives_write_errors(tmp_path: Path) -> None:
    path = tmp_path / "missing-dir" / "beat"
    heartbeat = Heartbeat(str(path), interval_seconds=0.02)

    heartbeat.start()
    await asyncio.sleep(0.05)
    os.makedirs(path.parent)
    await asyncio.sleep(0.1)
    recovered = path.exists()
    await heartbeat.stop()

    assert recovered, "heartbeat loop must keep running after failed writes"
