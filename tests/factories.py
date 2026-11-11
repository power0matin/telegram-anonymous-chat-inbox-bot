"""Small helpers that insert valid rows so tests only spell out what they are testing."""

import itertools
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from whisprlink.persistence.models import (
    InboxLink,
    InboxMessage,
    InboxThread,
    MessageDeliveryAttempt,
    RandomChatSession,
    User,
)
from whisprlink.persistence.models.enums import (
    DeliveryOutcome,
    InboxLinkStatus,
    MessageType,
    ParticipantRole,
    RandomSessionState,
    ThreadState,
)

_telegram_ids = itertools.count(1_000_000)
_hashes = itertools.count(1)
_source_ids = itertools.count(1)


async def make_user(session: AsyncSession, **overrides: Any) -> User:
    values: dict[str, Any] = {"telegram_user_id": next(_telegram_ids)}
    values.update(overrides)
    user = User(**values)
    session.add(user)
    await session.flush()
    return user


async def make_link(
    session: AsyncSession, owner: User, status: InboxLinkStatus = InboxLinkStatus.ACTIVE
) -> InboxLink:
    link = InboxLink(
        owner_id=owner.id,
        token_hash=next(_hashes).to_bytes(32, "big"),
        status=status,
    )
    session.add(link)
    await session.flush()
    return link


async def make_thread(
    session: AsyncSession,
    owner: User,
    sender: User,
    *,
    link: InboxLink | None = None,
    state: ThreadState = ThreadState.PENDING,
) -> InboxThread:
    link = link or await make_link(session, owner)
    thread = InboxThread(link_id=link.id, owner_id=owner.id, sender_id=sender.id, state=state)
    session.add(thread)
    await session.flush()
    return thread


async def make_message(
    session: AsyncSession,
    thread: InboxThread,
    role: ParticipantRole = ParticipantRole.SENDER,
    **overrides: Any,
) -> InboxMessage:
    values: dict[str, Any] = {
        "thread_id": thread.id,
        "sender_role": role,
        "message_type": MessageType.TEXT,
        "source_chat_id": 5_000_000_000 + next(_source_ids),
        "source_message_id": next(_source_ids),
    }
    values.update(overrides)
    message = InboxMessage(**values)
    session.add(message)
    await session.flush()
    return message


async def make_attempt(
    session: AsyncSession,
    message: InboxMessage,
    recipient: User,
    outcome: DeliveryOutcome = DeliveryOutcome.DELIVERED,
    attempt_number: int = 1,
) -> MessageDeliveryAttempt:
    finished = None if outcome is DeliveryOutcome.PENDING else datetime.now(UTC)
    attempt = MessageDeliveryAttempt(
        message_id=message.id,
        recipient_user_id=recipient.id,
        attempt_number=attempt_number,
        outcome=outcome,
        finished_at=finished,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def make_random_session(
    session: AsyncSession, state: RandomSessionState = RandomSessionState.SEARCHING
) -> RandomChatSession:
    started = datetime.now(UTC) if state is RandomSessionState.ACTIVE else None
    chat_session = RandomChatSession(state=state, started_at=started)
    session.add(chat_session)
    await session.flush()
    return chat_session
