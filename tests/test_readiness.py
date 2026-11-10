"""Startup dependency wait tests."""

import pytest

from whisprlink.infrastructure.readiness import DependencyUnavailableError, wait_until_ready


async def test_returns_as_soon_as_the_check_succeeds() -> None:
    calls = 0

    async def flaky() -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("not yet")

    await wait_until_ready(flaky, name="dep", attempts=5, delay_seconds=0)

    assert calls == 3


async def test_fails_after_the_bounded_number_of_attempts() -> None:
    calls = 0

    async def always_down() -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("down")

    with pytest.raises(DependencyUnavailableError, match="dep not ready after 3 attempts"):
        await wait_until_ready(always_down, name="dep", attempts=3, delay_seconds=0)

    assert calls == 3
