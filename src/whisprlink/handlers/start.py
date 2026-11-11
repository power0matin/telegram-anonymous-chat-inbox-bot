"""Start command handler."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message


async def handle_start(message: Message) -> None:
    """Confirm that the bot process is online without implying product features exist."""
    await message.answer(
        "WhisprLink is online.\n\n"
        "The project is currently in pre-alpha. Anonymous inbox and random chat "
        "features are still under development."
    )


def create_router() -> Router:
    """Build a fresh router; aiogram routers can be attached to only one dispatcher."""
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    return router
