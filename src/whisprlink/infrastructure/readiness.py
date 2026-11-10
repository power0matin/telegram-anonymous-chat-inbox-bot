"""Bounded wait-for-dependency helper used during startup."""

import asyncio
from collections.abc import Awaitable, Callable

from whisprlink.logging_config import get_logger

logger = get_logger(__name__)


class DependencyUnavailableError(RuntimeError):
    """A required dependency did not become ready within the allowed attempts."""


async def wait_until_ready(
    check: Callable[[], Awaitable[None]],
    *,
    name: str,
    attempts: int,
    delay_seconds: float,
) -> None:
    """Run ``check`` until it succeeds, failing after a bounded number of attempts."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await check()
        except Exception as exc:
            last_error = exc
            logger.warning(
                "dependency_not_ready",
                dependency=name,
                attempt=attempt,
                attempts=attempts,
                error_type=type(exc).__name__,
            )
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)
        else:
            logger.info("dependency_ready", dependency=name, attempt=attempt)
            return
    raise DependencyUnavailableError(
        f"{name} not ready after {attempts} attempts ({type(last_error).__name__})"
    ) from last_error
