"""Start command handler."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Confirm that the bot process is online without implying product features exist."""
    await message.answer(
        "WhisprLink is online.\n\n"
        "The project is currently in pre-alpha. Anonymous inbox and random chat "
        "features are still under development."
    )
