"""Application composition and polling entry point."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from whisprlink.config import get_settings
from whisprlink.handlers.start import router as start_router
from whisprlink.logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    """Build the dispatcher and register application routers."""
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    return dispatcher


async def run() -> None:
    """Start the Telegram bot using long polling."""
    settings = get_settings()
    configure_logging(settings.log_level)

    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    dispatcher = create_dispatcher()

    logger.info(
        "Starting WhisprLink",
        extra={"environment": settings.app_env, "mode": settings.bot_mode},
    )

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            close_bot_session=False,
        )
    finally:
        await bot.session.close()


def main() -> None:
    """CLI entry point."""
    asyncio.run(run())
