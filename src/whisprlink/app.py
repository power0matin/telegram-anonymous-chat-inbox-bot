"""Application composition, lifecycle, and command-line entry point."""

import argparse
import asyncio
import contextlib
import json
import signal
import sys
from collections.abc import Sequence

from aiogram import Bot, Dispatcher
from pydantic import ValidationError

from whisprlink.config import (
    InfrastructureSettings,
    Settings,
    get_infrastructure_settings,
    get_settings,
)
from whisprlink.handlers.start import create_router as create_start_router
from whisprlink.infrastructure.redis import RedisManager
from whisprlink.logging_config import configure_logging, get_logger
from whisprlink.observability.health import (
    HealthStatus,
    Heartbeat,
    check_liveness,
    check_readiness,
)
from whisprlink.persistence.database import Database

logger = get_logger(__name__)


def create_dispatcher() -> Dispatcher:
    """Build the dispatcher and register application routers."""
    dispatcher = Dispatcher()
    dispatcher.include_router(create_start_router())
    return dispatcher


class Application:
    """Owns every long-lived resource and the order in which they start and stop."""

    def __init__(self, settings: Settings, *, bot: Bot | None = None) -> None:
        self.settings = settings
        self.database = Database(settings)
        self.redis = RedisManager(settings)
        self.bot = bot or Bot(token=settings.telegram_bot_token.get_secret_value())
        self.dispatcher = create_dispatcher()
        self.dispatcher.workflow_data.update(
            settings=settings, database=self.database, redis=self.redis
        )
        self._heartbeat = Heartbeat(settings.heartbeat_path, settings.heartbeat_interval_seconds)
        self._stop_event = asyncio.Event()
        self._closed = False

    def request_stop(self) -> None:
        """Ask the running application to shut down gracefully (signal-handler safe)."""
        logger.info("shutdown_requested")
        self._stop_event.set()

    async def startup(self) -> None:
        """Wait for dependencies, then mark the process live. Fails after bounded retries."""
        logger.info(
            "starting",
            environment=self.settings.app_env,
            mode=self.settings.bot_mode,
        )
        await self.database.wait_until_ready()
        await self.redis.wait_until_ready()
        self._heartbeat.start()

    async def shutdown(self) -> None:
        """Release resources in reverse dependency order. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        steps = (
            ("heartbeat", self._heartbeat.stop),
            ("bot_session", self.bot.session.close),
            ("redis", self.redis.close),
            ("database", self.database.dispose),
        )
        for name, step in steps:
            try:
                await step()
            except Exception as exc:
                logger.error("shutdown_step_failed", step=name, error_type=type(exc).__name__)
        logger.info("stopped")

    async def run(self) -> None:
        """Start dependencies, poll Telegram until asked to stop, then shut down."""
        try:
            await self.startup()
            polling = asyncio.create_task(
                self.dispatcher.start_polling(
                    self.bot,
                    allowed_updates=self.dispatcher.resolve_used_update_types(),
                    handle_signals=False,
                    close_bot_session=False,
                ),
                name="polling",
            )
            stop_waiter = asyncio.create_task(self._stop_event.wait(), name="stop-waiter")
            done, _ = await asyncio.wait(
                {polling, stop_waiter}, return_when=asyncio.FIRST_COMPLETED
            )
            if polling in done:
                stop_waiter.cancel()
                polling.result()
                return
            try:
                await self.dispatcher.stop_polling()
            except RuntimeError:
                polling.cancel()
            await asyncio.gather(polling, return_exceptions=True)
        finally:
            await self.shutdown()


def _install_signal_handlers(application: Application) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, application.request_stop)


async def run(settings: Settings | None = None) -> None:
    """Start the Telegram bot using long polling."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    application = Application(settings)
    _install_signal_handlers(application)
    await application.run()


async def healthcheck(settings: InfrastructureSettings, *, liveness_only: bool) -> int:
    """Return a process exit code: 0 healthy, 1 unhealthy."""
    if liveness_only:
        alive = check_liveness(
            settings.heartbeat_path, max_age_seconds=settings.heartbeat_max_age_seconds
        )
        print(json.dumps({"liveness": alive}))
        return 0 if alive else 1

    database = Database(settings)
    redis = RedisManager(settings)
    try:
        report = await check_readiness(
            database.ping,
            redis.ping,
            timeout_seconds=settings.health_check_timeout_seconds,
        )
    finally:
        await redis.close()
        await database.dispose()
    print(json.dumps(report.as_dict()))
    return 0 if report.status is HealthStatus.OK else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="whisprlink", description="WhisprLink Telegram bot")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("run", help="start the bot with long polling (default)")
    check = subcommands.add_parser("healthcheck", help="probe PostgreSQL/Redis or process liveness")
    check.add_argument(
        "--liveness",
        action="store_true",
        help="only verify the running process heartbeat instead of dependencies",
    )
    return parser


def _report_invalid_configuration(error: ValidationError) -> None:
    """Print which settings are invalid without echoing their (possibly secret) values."""
    print("Invalid configuration:", file=sys.stderr)
    for item in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "settings"
        print(f"  - {location.upper()}: {item['msg']}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point."""
    args = _build_parser().parse_args(argv)
    command = args.command or "run"
    try:
        if command == "healthcheck":
            infrastructure = get_infrastructure_settings()
            configure_logging("WARNING", infrastructure.log_format, stream=sys.stderr)
            raise SystemExit(asyncio.run(healthcheck(infrastructure, liveness_only=args.liveness)))
        asyncio.run(run())
    except ValidationError as error:
        _report_invalid_configuration(error)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
