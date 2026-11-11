"""Concurrency-critical invariants hold under real parallel transactions."""

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from tests.factories import make_link, make_random_session, make_thread, make_user
from whisprlink.persistence.database import Database
from whisprlink.persistence.models import (
    InboxLink,
    OutboxEvent,
    RandomChatParticipant,
    RandomChatSession,
)
from whisprlink.persistence.models.enums import InboxLinkStatus

pytestmark = pytest.mark.integration

PARALLELISM = 20


async def test_a_user_wins_at_most_one_of_many_simultaneous_matches(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session)

    async def try_to_join() -> bool:
        try:
            async with database.transaction() as session:
                chat = await make_random_session(session)
                session.add(RandomChatParticipant(session_id=chat.id, user_id=user.id, slot=1))
        except IntegrityError:
            return False
        return True

    results = await asyncio.gather(*(try_to_join() for _ in range(PARALLELISM)))

    assert sum(results) == 1
    async with database.session() as session:
        memberships = await session.scalar(
            sa.select(sa.func.count()).select_from(RandomChatParticipant)
        )
        sessions = await session.scalar(sa.select(sa.func.count()).select_from(RandomChatSession))
    assert (memberships, sessions) == (1, 1)  # losing transactions left no orphan sessions


async def test_concurrent_outbox_inserts_with_one_key_create_one_event(database: Database) -> None:
    statement = (
        pg_insert(OutboxEvent)
        .values(
            event_type="notify_new_message",
            aggregate_type="thread",
            aggregate_id=1,
            idempotency_key="thread:1:notify",
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(OutboxEvent.id)
    )

    async def enqueue() -> int | None:
        async with database.transaction() as session:
            return (await session.execute(statement)).scalar_one_or_none()

    results = await asyncio.gather(*(enqueue() for _ in range(PARALLELISM)))

    assert sum(1 for result in results if result is not None) == 1


async def test_link_rotation_waits_for_an_in_flight_thread_and_then_blocks_new_ones(
    database: Database,
) -> None:
    async with database.transaction() as session:
        owner, sender = await make_user(session), await make_user(session)
        link = await make_link(session, owner)

    thread_inserted = asyncio.Event()
    release_thread_transaction = asyncio.Event()

    async def create_thread_slowly() -> None:
        async with database.transaction() as session:
            await make_thread(session, owner, sender, link=link)
            thread_inserted.set()
            await release_thread_transaction.wait()

    async def rotate() -> None:
        async with database.transaction() as session:
            await session.execute(
                sa.update(InboxLink)
                .where(InboxLink.id == link.id)
                .values(status=InboxLinkStatus.ROTATED)
            )

    creator = asyncio.create_task(create_thread_slowly())
    await thread_inserted.wait()
    rotation = asyncio.create_task(rotate())
    await asyncio.sleep(0.5)

    assert not rotation.done(), "rotation must wait for the in-flight thread insert"

    release_thread_transaction.set()
    await asyncio.gather(creator, rotation)

    async with database.session() as session:
        with pytest.raises(IntegrityError, match="inbox link is not active"):
            await make_thread(session, owner, sender, link=link)

async def test_session_close_waits_for_in_flight_participant_insert(
    database: Database,
) -> None:
    async with database.transaction() as session:
        user = await make_user(session)
        chat = await make_random_session(session)

    participant_inserted = asyncio.Event()
    release_insert_transaction = asyncio.Event()
    close_started = asyncio.Event()

    async def join_slowly() -> None:
        async with database.transaction() as session:
            session.add(RandomChatParticipant(session_id=chat.id, user_id=user.id, slot=1))
            await session.flush()
            participant_inserted.set()
            await release_insert_transaction.wait()

    async def close_session() -> None:
        close_started.set()
        async with database.transaction() as session:
            await session.execute(
                sa.text(
                    "UPDATE random_chat_sessions SET state = 'closed', ended_at = now(), "
                    "end_reason = 'cancelled' WHERE id = :id"
                ),
                {"id": chat.id},
            )

    join_task = asyncio.create_task(join_slowly())
    close_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(participant_inserted.wait(), timeout=5)
        close_task = asyncio.create_task(close_session())
        await asyncio.wait_for(close_started.wait(), timeout=5)
        await asyncio.sleep(0.25)

        assert not close_task.done(), "closing must wait for the in-flight membership insert"
    finally:
        release_insert_transaction.set()
        tasks = [join_task]
        if close_task is not None:
            tasks.append(close_task)
        await asyncio.gather(*tasks, return_exceptions=True)

    async with database.session() as session:
        participant = await session.scalar(
            sa.select(RandomChatParticipant).where(
                RandomChatParticipant.session_id == chat.id,
                RandomChatParticipant.user_id == user.id,
            )
        )

    assert participant is not None
    assert participant.left_at is not None, "closing must release the just-inserted participant"
