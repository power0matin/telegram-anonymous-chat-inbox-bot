"""The installed entry point behaves correctly as a real process."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


async def run_cli(tmp_path: Path, *args: str, **env: str) -> tuple[int, str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("TEST_")}
    environment.update(env)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "whisprlink",
        *args,
        cwd=tmp_path,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    assert process.returncode is not None
    return process.returncode, stdout.decode(), stderr.decode()


async def test_healthcheck_process_reports_ok_without_a_telegram_token(
    migrated_database_url: str, redis_test_url: str, tmp_path: Path
) -> None:
    code, stdout, _ = await run_cli(
        tmp_path, "healthcheck", DATABASE_URL=migrated_database_url, REDIS_URL=redis_test_url
    )

    assert code == 0
    assert json.loads(stdout)["status"] == "ok"


async def test_healthcheck_process_exits_non_zero_when_redis_is_down(
    migrated_database_url: str, tmp_path: Path
) -> None:
    code, stdout, _ = await run_cli(
        tmp_path,
        "healthcheck",
        DATABASE_URL=migrated_database_url,
        REDIS_URL="redis://127.0.0.1:1/0",
        REDIS_RETRY_ATTEMPTS="0",
    )

    assert code == 1
    assert json.loads(stdout)["status"] == "degraded"


async def test_run_process_exits_with_code_2_on_invalid_configuration(tmp_path: Path) -> None:
    code, stdout, stderr = await run_cli(
        tmp_path,
        "run",
        APP_ENV="production",
        TELEGRAM_BOT_TOKEN="123456:not-a-real-token",
        DEEP_LINK_SECRET="s3cret-that-must-not-be-printed-anywhere-123",
    )

    assert code == 2
    assert "Invalid configuration" in stderr
    assert "s3cret-that-must-not-be-printed" not in stdout + stderr
