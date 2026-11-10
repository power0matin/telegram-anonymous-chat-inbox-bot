"""Readiness probing against real and unreachable dependencies."""

import json

import pytest

from tests.conftest import infrastructure_settings
from whisprlink.app import healthcheck
from whisprlink.config import InfrastructureSettings

pytestmark = pytest.mark.integration

DEAD_DATABASE = "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none"
DEAD_REDIS = "redis://127.0.0.1:1/0"


def settings(database_url: str, redis_url: str) -> InfrastructureSettings:
    return infrastructure_settings(
        database_url,
        redis_url,
        health_check_timeout_seconds=2.0,
        redis_retry_attempts=0,
        db_connect_timeout_seconds=1.0,
    )


async def test_everything_up_reports_ok(
    migrated_database_url: str, redis_test_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await healthcheck(settings(migrated_database_url, redis_test_url), liveness_only=False)

    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0
    assert report["status"] == "ok"
    assert report["components"]["database"]["healthy"] is True


async def test_redis_down_is_degraded_and_unhealthy_for_the_probe(
    migrated_database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await healthcheck(settings(migrated_database_url, DEAD_REDIS), liveness_only=False)

    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 1
    assert report["status"] == "degraded"
    assert report["components"]["redis"]["error_type"] is not None


async def test_database_down_is_unavailable(
    redis_test_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await healthcheck(settings(DEAD_DATABASE, redis_test_url), liveness_only=False)

    assert code == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "unavailable"
