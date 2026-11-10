"""Every invariant the schema promises is enforced by PostgreSQL, not by Python."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    make_attempt,
    make_link,
    make_message,
    make_random_session,
    make_thread,
    make_user,
)
from whisprlink.persistence.database import Database
from whisprlink.persistence.models import (
    AdminAuditLog,
    Block,
    InboxLink,
    InboxOpenEvent,
    InboxThread,
    MessageDeliveryAttempt,
    MessageMediaItem,
    OutboxEvent,
    RandomChatParticipant,
    Report,
    TelegramUpdateReceipt,
    User,
    UserConsent,
)
from whisprlink.persistence.models.enums import (
    BlockScope,
    ConsentType,
    DeliveryOutcome,
    InboxLinkStatus,
    MessageType,
    OutboxState,
    ParticipantRole,
    RandomEndReason,
    RandomSessionState,
    ReportCategory,
    ThreadState,
    UserStatus,
)

pytestmark = pytest.mark.integration


@asynccontextmanager
async def rejected(database: Database, match: str) -> AsyncIterator[AsyncSession]:
    """Run the body in a fresh session and require PostgreSQL to reject it."""
    async with database.session() as session:
        with pytest.raises(IntegrityError, match=match):
            yield session
            await session.flush()


@dataclass(frozen=True)
class World:
    owner: User
    sender: User
    other: User
    link: InboxLink


@pytest.fixture
async def world(database: Database) -> World:
    async with database.transaction() as session:
        owner = await make_user(session)
        sender = await make_user(session)
        other = await make_user(session)
        link = await make_link(session, owner)
    return World(owner, sender, other, link)


async def scalar(database: Database, query: str, **params: object) -> object:
    async with database.session() as session:
        return (await session.execute(sa.text(query), params)).scalar_one()


# --- users -------------------------------------------------------------------------------------


async def test_telegram_user_id_is_unique(database: Database) -> None:
    async with database.transaction() as session:
        session.add(User(telegram_user_id=77))

    async with rejected(database, "uq_users_telegram_user_id") as session:
        session.add(User(telegram_user_id=77))


async def test_telegram_user_id_must_be_positive(database: Database) -> None:
    async with rejected(database, "ck_users_telegram_user_id_positive") as session:
        session.add(User(telegram_user_id=0))


async def test_deleted_users_are_tombstones_without_a_telegram_id(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session)

    async with rejected(database, "ck_users_deleted_iff_deleted_at") as session:
        await session.execute(sa.update(User).where(User.id == user.id).values(status="deleted"))

    async with rejected(database, "ck_users_deleted_iff_no_telegram_id") as session:
        await session.execute(
            sa.update(User)
            .where(User.id == user.id)
            .values(status="deleted", deleted_at=sa.func.now())
        )

    async with rejected(database, "ck_users_deleted_iff_no_telegram_id") as session:
        session.add(User(telegram_user_id=None))


async def test_tombstoning_frees_the_telegram_id_for_re_registration(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session, telegram_user_id=4242)
        await session.execute(
            sa.update(User)
            .where(User.id == user.id)
            .values(status=UserStatus.DELETED, telegram_user_id=None, deleted_at=sa.func.now())
        )
        session.add(User(telegram_user_id=4242))

    assert await scalar(database, "SELECT count(*) FROM users") == 2


async def test_consent_is_unique_per_type_and_version(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session)
        session.add(UserConsent(user_id=user.id, consent_type=ConsentType.RULES, version="1"))
        session.add(UserConsent(user_id=user.id, consent_type=ConsentType.RULES, version="2"))

    async with rejected(database, "uq_user_consents_user_type_version") as session:
        session.add(UserConsent(user_id=user.id, consent_type=ConsentType.RULES, version="2"))


# --- inbox links -------------------------------------------------------------------------------


async def test_token_hash_must_be_32_bytes_and_unique(database: Database, world: World) -> None:
    async with rejected(database, "ck_inbox_links_token_hash_length") as session:
        session.add(InboxLink(owner_id=world.sender.id, token_hash=b"short"))

    async with database.transaction() as session:
        session.add(
            InboxLink(
                owner_id=world.sender.id, token_hash=b"\x01" * 32, status=InboxLinkStatus.DISABLED
            )
        )
    async with rejected(database, "uq_inbox_links_token_hash") as session:
        session.add(
            InboxLink(
                owner_id=world.other.id, token_hash=b"\x01" * 32, status=InboxLinkStatus.DISABLED
            )
        )


async def test_an_owner_has_at_most_one_live_link_but_rotation_frees_the_slot(
    database: Database, world: World
) -> None:
    async with rejected(database, "uq_inbox_links_one_live_link_per_owner") as session:
        await make_link(session, world.owner)

    async with database.transaction() as session:
        await session.execute(
            sa.update(InboxLink)
            .where(InboxLink.id == world.link.id)
            .values(status=InboxLinkStatus.PAUSED)
        )
    async with rejected(database, "uq_inbox_links_one_live_link_per_owner") as session:
        await make_link(session, world.owner)  # a paused link still occupies the slot

    async with database.transaction() as session:
        await session.execute(
            sa.update(InboxLink)
            .where(InboxLink.id == world.link.id)
            .values(status=InboxLinkStatus.ROTATED)
        )
        await make_link(session, world.owner)

    assert await scalar(database, "SELECT count(*) FROM inbox_links") == 2


# --- threads -----------------------------------------------------------------------------------


async def test_thread_creation_succeeds_through_an_active_link(
    database: Database, world: World
) -> None:
    async with database.transaction() as session:
        await make_thread(session, world.owner, world.sender, link=world.link)

    assert await scalar(database, "SELECT count(*) FROM inbox_threads") == 1


@pytest.mark.parametrize(
    "status", [InboxLinkStatus.PAUSED, InboxLinkStatus.DISABLED, InboxLinkStatus.ROTATED]
)
async def test_inactive_links_cannot_create_threads(
    database: Database, world: World, status: InboxLinkStatus
) -> None:
    async with database.transaction() as session:
        await session.execute(
            sa.update(InboxLink).where(InboxLink.id == world.link.id).values(status=status)
        )

    async with rejected(database, "inbox link is not active") as session:
        await make_thread(session, world.owner, world.sender, link=world.link)


async def test_a_link_cannot_create_threads_for_another_owner(
    database: Database, world: World
) -> None:
    async with rejected(database, "inbox link is not active") as session:
        await make_thread(session, world.other, world.sender, link=world.link)


async def test_a_user_cannot_open_a_thread_with_themselves(
    database: Database, world: World
) -> None:
    async with rejected(database, "ck_inbox_threads_owner_differs_from_sender") as session:
        await make_thread(session, world.owner, world.owner, link=world.link)


@pytest.mark.parametrize("blocker_is_owner", [True, False])
async def test_blocked_pairs_cannot_create_threads_in_either_direction(
    database: Database, world: World, blocker_is_owner: bool
) -> None:
    blocker, blocked = (
        (world.owner, world.sender) if blocker_is_owner else (world.sender, world.owner)
    )
    async with database.transaction() as session:
        session.add(Block(blocker_id=blocker.id, blocked_id=blocked.id, scope=BlockScope.INBOX))

    async with rejected(database, "participants are blocked") as session:
        await make_thread(session, world.owner, world.sender, link=world.link)


async def test_random_chat_blocks_do_not_affect_the_inbox(database: Database, world: World) -> None:
    async with database.transaction() as session:
        session.add(
            Block(
                blocker_id=world.owner.id, blocked_id=world.sender.id, scope=BlockScope.RANDOM_CHAT
            )
        )
        await make_thread(session, world.owner, world.sender, link=world.link)


async def test_closed_state_requires_closer_and_timestamp(database: Database, world: World) -> None:
    async with rejected(database, "ck_inbox_threads_closed_iff_closed_at") as session:
        await make_thread(
            session, world.owner, world.sender, link=world.link, state=ThreadState.CLOSED
        )


# --- messages ----------------------------------------------------------------------------------


@pytest.fixture
async def thread_id(database: Database, world: World) -> int:
    async with database.transaction() as session:
        thread = await make_thread(
            session, world.owner, world.sender, link=world.link, state=ThreadState.OPEN
        )
    return thread.id


async def test_reply_targets_must_belong_to_the_same_thread(
    database: Database, world: World, thread_id: int
) -> None:
    async with database.transaction() as session:
        first = await make_message(session, InboxThread(id=thread_id))
        reply = await make_message(
            session,
            InboxThread(id=thread_id),
            ParticipantRole.OWNER,
            reply_to_message_id=first.id,
        )
        second_link = await make_link(session, world.other)
        other_thread = await make_thread(session, world.other, world.sender, link=second_link)
        foreign = await make_message(session, other_thread)

    assert reply.reply_to_message_id == first.id
    async with rejected(database, "fk_inbox_messages_reply_target_same_thread") as session:
        await make_message(
            session,
            InboxThread(id=thread_id),
            ParticipantRole.OWNER,
            reply_to_message_id=foreign.id,
        )


async def test_a_message_cannot_reply_to_itself(database: Database, thread_id: int) -> None:
    async with database.transaction() as session:
        message = await make_message(session, InboxThread(id=thread_id))

    async with rejected(database, "ck_inbox_messages_reply_not_self") as session:
        await session.execute(
            sa.text("UPDATE inbox_messages SET reply_to_message_id = id WHERE id = :id"),
            {"id": message.id},
        )


async def test_the_same_telegram_message_cannot_be_recorded_twice(
    database: Database, thread_id: int
) -> None:
    async with database.transaction() as session:
        await make_message(
            session, InboxThread(id=thread_id), source_chat_id=9, source_message_id=9
        )

    async with rejected(database, "uq_inbox_messages_source_message") as session:
        await make_message(
            session, InboxThread(id=thread_id), source_chat_id=9, source_message_id=9
        )


async def test_closed_threads_reject_new_messages(database: Database, thread_id: int) -> None:
    async with database.transaction() as session:
        await session.execute(
            sa.text(
                "UPDATE inbox_threads SET state = 'closed', closed_at = now(), "
                "closed_by = 'owner' WHERE id = :id"
            ),
            {"id": thread_id},
        )

    async with rejected(database, "thread is closed") as session:
        await make_message(session, InboxThread(id=thread_id))


async def test_owner_cannot_reply_before_the_thread_is_opened(
    database: Database, world: World
) -> None:
    async with database.transaction() as session:
        pending = await make_thread(session, world.owner, world.sender, link=world.link)

    async with database.transaction() as session:
        await make_message(session, pending, ParticipantRole.SENDER)

    async with rejected(database, "owner cannot reply before opening") as session:
        await make_message(session, pending, ParticipantRole.OWNER)


async def test_blocking_after_the_fact_stops_new_messages_in_existing_threads(
    database: Database, world: World, thread_id: int
) -> None:
    async with database.transaction() as session:
        await make_message(session, InboxThread(id=thread_id), ParticipantRole.SENDER)
        session.add(
            Block(blocker_id=world.owner.id, blocked_id=world.sender.id, scope=BlockScope.INBOX)
        )

    async with rejected(database, "participants are blocked") as session:
        await make_message(session, InboxThread(id=thread_id), ParticipantRole.SENDER)
    async with rejected(database, "participants are blocked") as session:
        await make_message(session, InboxThread(id=thread_id), ParticipantRole.OWNER)


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("message_type", "carrier_pigeon", "ck_inbox_messages_message_type"),
        ("sender_role", "stranger", "ck_inbox_messages_participant_role"),
    ],
)
async def test_enum_columns_reject_unknown_values_at_the_database(
    database: Database, thread_id: int, column: str, value: str, constraint: str
) -> None:
    values = {"message_type": "text", "sender_role": "sender", column: value}
    async with rejected(database, constraint) as session:
        await session.execute(
            sa.text(
                "INSERT INTO inbox_messages (thread_id, sender_role, message_type, "
                "source_chat_id, source_message_id) VALUES (:t, :sender_role, :message_type, 1, 1)"
            ),
            {"t": thread_id, **values},
        )


async def test_media_items_are_ordered_and_deduplicated(database: Database, thread_id: int) -> None:
    async with database.transaction() as session:
        message = await make_message(
            session, InboxThread(id=thread_id), message_type=MessageType.ALBUM
        )
        session.add(
            MessageMediaItem(
                message_id=message.id,
                position=0,
                media_type=MessageType.PHOTO,
                source_chat_id=1,
                source_message_id=1,
            )
        )

    def item(position: int, source_message_id: int) -> MessageMediaItem:
        return MessageMediaItem(
            message_id=message.id,
            position=position,
            media_type=MessageType.PHOTO,
            source_chat_id=1,
            source_message_id=source_message_id,
        )

    async with rejected(database, "uq_message_media_items_position") as session:
        session.add(item(0, 2))
    async with rejected(database, "uq_message_media_items_source_message") as session:
        session.add(item(1, 1))
    async with rejected(database, "ck_message_media_items_position_non_negative") as session:
        session.add(item(-1, 3))


async def test_deleting_a_thread_removes_its_messages_media_attempts_and_receipts(
    database: Database, world: World, thread_id: int
) -> None:
    async with database.transaction() as session:
        message = await make_message(session, InboxThread(id=thread_id))
        session.add(
            MessageMediaItem(
                message_id=message.id,
                position=0,
                media_type=MessageType.PHOTO,
                source_chat_id=1,
                source_message_id=1,
            )
        )
        attempt = await make_attempt(session, message, world.owner)
        session.add(
            InboxOpenEvent(
                thread_id=thread_id,
                message_id=message.id,
                opened_by_user_id=world.owner.id,
                delivery_attempt_id=attempt.id,
            )
        )

    async with database.transaction() as session:
        await session.execute(sa.delete(InboxThread).where(InboxThread.id == thread_id))

    for table in (
        "inbox_messages",
        "message_media_items",
        "message_delivery_attempts",
        "inbox_open_events",
    ):
        assert await scalar(database, f"SELECT count(*) FROM {table}") == 0, table


# --- delivery attempts and open receipts -------------------------------------------------------


@dataclass(frozen=True)
class OpenScenario:
    world: World
    thread_id: int
    message_id: int


@pytest.fixture
async def scenario(database: Database, world: World, thread_id: int) -> OpenScenario:
    async with database.transaction() as session:
        message = await make_message(session, InboxThread(id=thread_id), ParticipantRole.SENDER)
    return OpenScenario(world, thread_id, message.id)


def open_event(scenario: OpenScenario, attempt_id: int, **overrides: object) -> InboxOpenEvent:
    values: dict[str, object] = {
        "thread_id": scenario.thread_id,
        "message_id": scenario.message_id,
        "opened_by_user_id": scenario.world.owner.id,
        "delivery_attempt_id": attempt_id,
    }
    values.update(overrides)
    return InboxOpenEvent(**values)


async def attempt_for(
    database: Database,
    scenario: OpenScenario,
    outcome: DeliveryOutcome,
    *,
    message_id: int | None = None,
    recipient_user_id: int | None = None,
) -> int:
    async with database.transaction() as session:
        attempt = MessageDeliveryAttempt(
            message_id=message_id or scenario.message_id,
            recipient_user_id=recipient_user_id or scenario.world.owner.id,
            attempt_number=1,
            outcome=outcome,
            finished_at=None if outcome is DeliveryOutcome.PENDING else sa.func.now(),
        )
        session.add(attempt)
    return attempt.id


async def test_open_receipt_is_recorded_after_a_delivered_attempt(
    database: Database, scenario: OpenScenario
) -> None:
    attempt_id = await attempt_for(database, scenario, DeliveryOutcome.DELIVERED)

    async with database.transaction() as session:
        session.add(open_event(scenario, attempt_id))

    assert await scalar(database, "SELECT count(*) FROM inbox_open_events") == 1


@pytest.mark.parametrize(
    "outcome",
    [
        DeliveryOutcome.PENDING,
        DeliveryOutcome.FAILED_TRANSIENT,
        DeliveryOutcome.FAILED_PERMANENT,
        DeliveryOutcome.AMBIGUOUS,
    ],
)
async def test_open_receipt_is_impossible_without_successful_delivery(
    database: Database, scenario: OpenScenario, outcome: DeliveryOutcome
) -> None:
    attempt_id = await attempt_for(database, scenario, outcome)

    async with rejected(database, "fk_inbox_open_events_delivered_attempt") as session:
        session.add(open_event(scenario, attempt_id))


async def test_open_receipt_cannot_claim_a_non_delivered_outcome(
    database: Database, scenario: OpenScenario
) -> None:
    attempt_id = await attempt_for(database, scenario, DeliveryOutcome.FAILED_PERMANENT)

    async with rejected(database, "ck_inbox_open_events_requires_delivered_attempt") as session:
        session.add(
            open_event(scenario, attempt_id, attempt_outcome=DeliveryOutcome.FAILED_PERMANENT)
        )


async def test_open_receipt_must_use_an_attempt_for_the_same_message(
    database: Database, scenario: OpenScenario
) -> None:
    async with database.transaction() as session:
        unrelated = await make_message(
            session, InboxThread(id=scenario.thread_id), ParticipantRole.SENDER
        )
    foreign_attempt = await attempt_for(
        database, scenario, DeliveryOutcome.DELIVERED, message_id=unrelated.id
    )

    async with rejected(database, "fk_inbox_open_events_delivered_attempt") as session:
        session.add(open_event(scenario, foreign_attempt))


async def test_only_the_recipient_can_open_a_message(
    database: Database, scenario: OpenScenario
) -> None:
    attempt_id = await attempt_for(database, scenario, DeliveryOutcome.DELIVERED)

    for intruder in (scenario.world.sender, scenario.world.other):
        async with rejected(database, "only the message recipient can open it") as session:
            session.add(open_event(scenario, attempt_id, opened_by_user_id=intruder.id))


async def test_open_receipt_must_match_the_delivery_attempt_recipient(
    database: Database, scenario: OpenScenario
) -> None:
    attempt_id = await attempt_for(
        database,
        scenario,
        DeliveryOutcome.DELIVERED,
        recipient_user_id=scenario.world.sender.id,
    )

    async with rejected(database, "delivery attempt recipient does not match opener") as session:
        session.add(open_event(scenario, attempt_id))


async def test_a_message_can_be_opened_only_once(
    database: Database, scenario: OpenScenario
) -> None:
    attempt_id = await attempt_for(database, scenario, DeliveryOutcome.DELIVERED)
    async with database.transaction() as session:
        session.add(open_event(scenario, attempt_id))

    async with rejected(database, "uq_inbox_open_events_message_id") as session:
        session.add(open_event(scenario, attempt_id))


async def test_a_delivered_attempt_cannot_be_downgraded_after_a_receipt_exists(
    database: Database, scenario: OpenScenario
) -> None:
    attempt_id = await attempt_for(database, scenario, DeliveryOutcome.DELIVERED)
    async with database.transaction() as session:
        session.add(open_event(scenario, attempt_id))

    async with rejected(database, "violates foreign key constraint") as session:
        await session.execute(
            sa.update(MessageDeliveryAttempt)
            .where(MessageDeliveryAttempt.id == attempt_id)
            .values(outcome=DeliveryOutcome.FAILED_PERMANENT)
        )


async def test_delivery_attempts_are_sequenced_and_finished_consistently(
    database: Database, scenario: OpenScenario
) -> None:
    await attempt_for(database, scenario, DeliveryOutcome.FAILED_TRANSIENT)

    async with rejected(database, "uq_message_delivery_attempts_sequence") as session:
        session.add(
            MessageDeliveryAttempt(
                message_id=scenario.message_id,
                recipient_user_id=scenario.world.owner.id,
                attempt_number=1,
            )
        )
    async with rejected(
        database, "ck_message_delivery_attempts_finished_iff_not_pending"
    ) as session:
        session.add(
            MessageDeliveryAttempt(
                message_id=scenario.message_id,
                recipient_user_id=scenario.world.owner.id,
                attempt_number=2,
                outcome=DeliveryOutcome.PENDING,
                finished_at=sa.func.now(),
            )
        )


# --- random chat -------------------------------------------------------------------------------


async def join(session: AsyncSession, session_id: int, user_id: int, slot: int) -> None:
    session.add(RandomChatParticipant(session_id=session_id, user_id=user_id, slot=slot))
    await session.flush()


async def test_a_user_can_have_only_one_active_membership(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session)
        first = await make_random_session(session)
        second = await make_random_session(session)
        await join(session, first.id, user.id, 1)

    async with rejected(database, "uq_random_chat_participants_one_active_membership") as session:
        await join(session, second.id, user.id, 1)


async def test_leaving_frees_the_user_for_another_session(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session)
        first = await make_random_session(session)
        second = await make_random_session(session)
        await join(session, first.id, user.id, 1)
        await session.execute(
            sa.update(RandomChatParticipant)
            .where(RandomChatParticipant.session_id == first.id)
            .values(left_at=sa.func.now(), left_reason=RandomEndReason.SKIPPED)
        )
        await join(session, second.id, user.id, 1)

    assert await scalar(database, "SELECT count(*) FROM random_chat_participants") == 2


async def test_a_session_holds_at_most_two_distinct_participants(database: Database) -> None:
    async with database.transaction() as session:
        a, b, c = [await make_user(session) for _ in range(3)]
        chat = await make_random_session(session)
        await join(session, chat.id, a.id, 1)
        await join(session, chat.id, b.id, 2)

    async with rejected(database, "ck_random_chat_participants_slot_range") as session:
        await join(session, chat.id, c.id, 3)
    async with rejected(database, "uq_random_chat_participants_slot") as session:
        await join(session, chat.id, c.id, 2)
    async with database.transaction() as session:
        solo = await make_random_session(session)
        d = await make_user(session)
        await join(session, solo.id, d.id, 1)
    async with rejected(database, "uq_random_chat_participants_user") as session:
        await join(session, solo.id, d.id, 2)


async def test_closing_a_session_releases_both_participants(database: Database) -> None:
    async with database.transaction() as session:
        a, b = await make_user(session), await make_user(session)
        chat = await make_random_session(session, RandomSessionState.ACTIVE)
        await join(session, chat.id, a.id, 1)
        await join(session, chat.id, b.id, 2)

    async with database.transaction() as session:
        await session.execute(
            sa.text(
                "UPDATE random_chat_sessions SET state = 'closed', ended_at = now(), "
                "end_reason = 'skipped' WHERE id = :id"
            ),
            {"id": chat.id},
        )

    assert (
        await scalar(
            database,
            "SELECT count(*) FROM random_chat_participants "
            "WHERE left_at IS NOT NULL AND left_reason = 'skipped'",
        )
        == 2
    )
    async with database.transaction() as session:
        fresh = await make_random_session(session)
        await join(session, fresh.id, a.id, 1)  # no longer "busy"


async def test_closed_sessions_accept_no_participants(database: Database) -> None:
    async with database.transaction() as session:
        user = await make_user(session)
        chat = await make_random_session(session)
        await session.execute(
            sa.text(
                "UPDATE random_chat_sessions SET state = 'closed', ended_at = now(), "
                "end_reason = 'cancelled' WHERE id = :id"
            ),
            {"id": chat.id},
        )

    async with rejected(database, "session is closed") as session:
        await join(session, chat.id, user.id, 1)


@pytest.mark.parametrize("blocker_is_first", [True, False])
async def test_blocked_users_cannot_share_a_session(
    database: Database, blocker_is_first: bool
) -> None:
    async with database.transaction() as session:
        first, second = await make_user(session), await make_user(session)
        chat = await make_random_session(session)
        await join(session, chat.id, first.id, 1)
        blocker, blocked = (first, second) if blocker_is_first else (second, first)
        session.add(
            Block(blocker_id=blocker.id, blocked_id=blocked.id, scope=BlockScope.RANDOM_CHAT)
        )

    async with rejected(database, "participants are blocked") as session:
        await join(session, chat.id, second.id, 2)


@pytest.mark.parametrize("status", [UserStatus.RESTRICTED, UserStatus.BANNED])
async def test_restricted_and_banned_users_cannot_join(
    database: Database, status: UserStatus
) -> None:
    async with database.transaction() as session:
        user = await make_user(session, status=status)
        chat = await make_random_session(session)

    async with rejected(database, "user is not eligible for random chat") as session:
        await join(session, chat.id, user.id, 1)


async def test_session_state_must_match_its_timestamps(database: Database) -> None:
    async with rejected(database, "ck_random_chat_sessions_started_iff_matched") as session:
        await session.execute(sa.text("INSERT INTO random_chat_sessions (state) VALUES ('active')"))
    async with rejected(database, "ck_random_chat_sessions_closed_iff_end_reason") as session:
        await session.execute(
            sa.text("INSERT INTO random_chat_sessions (state, ended_at) VALUES ('closed', now())")
        )


# --- blocks, reports, outbox, receipts, audit --------------------------------------------------


async def test_blocks_are_unique_per_pair_and_scope_and_never_self_directed(
    database: Database,
) -> None:
    async with database.transaction() as session:
        a, b = await make_user(session), await make_user(session)
        session.add(Block(blocker_id=a.id, blocked_id=b.id, scope=BlockScope.INBOX))
        session.add(Block(blocker_id=a.id, blocked_id=b.id, scope=BlockScope.RANDOM_CHAT))

    async with rejected(database, "uq_blocks_pair_scope") as session:
        session.add(Block(blocker_id=a.id, blocked_id=b.id, scope=BlockScope.INBOX))
    async with rejected(database, "ck_blocks_no_self_block") as session:
        session.add(Block(blocker_id=a.id, blocked_id=a.id, scope=BlockScope.INBOX))


async def test_reports_reject_self_reports_and_inconsistent_resolution(database: Database) -> None:
    async with database.transaction() as session:
        a, b = await make_user(session), await make_user(session)

    async with rejected(database, "ck_reports_no_self_report") as session:
        session.add(Report(reporter_id=a.id, reported_id=a.id, category=ReportCategory.SPAM))
    async with rejected(database, "ck_reports_resolved_iff_resolved_at") as session:
        session.add(
            Report(
                reporter_id=a.id,
                reported_id=b.id,
                category=ReportCategory.SPAM,
                status="resolved",
            )
        )


async def test_outbox_idempotency_keys_are_unique(database: Database) -> None:
    def event(key: str) -> OutboxEvent:
        return OutboxEvent(
            event_type="notify_new_message",
            aggregate_type="thread",
            aggregate_id=1,
            idempotency_key=key,
        )

    async with database.transaction() as session:
        session.add(event("thread:1:notify"))

    async with rejected(database, "uq_outbox_events_idempotency_key") as session:
        session.add(event("thread:1:notify"))


async def test_a_processing_outbox_event_must_hold_a_lease(database: Database) -> None:
    async with rejected(database, "ck_outbox_events_processing_requires_lease") as session:
        session.add(
            OutboxEvent(
                event_type="x",
                aggregate_type="thread",
                aggregate_id=1,
                idempotency_key="k1",
                state=OutboxState.PROCESSING,
            )
        )

    async with database.transaction() as session:
        session.add(
            OutboxEvent(
                event_type="x",
                aggregate_type="thread",
                aggregate_id=1,
                idempotency_key="k2",
                state=OutboxState.PROCESSING,
                lease_owner="worker-1",
                lease_expires_at=sa.func.now() + sa.text("interval '30 seconds'"),
            )
        )


async def test_duplicate_telegram_updates_are_detectable(database: Database) -> None:
    statement = (
        pg_insert(TelegramUpdateReceipt)
        .values(update_id=555)
        .on_conflict_do_nothing()
        .returning(TelegramUpdateReceipt.update_id)
    )

    async with database.transaction() as session:
        first = (await session.execute(statement)).scalar_one_or_none()
        second = (await session.execute(statement)).scalar_one_or_none()

    assert (first, second) == (555, None)
    async with rejected(database, "pk_telegram_update_receipts") as session:
        session.add(TelegramUpdateReceipt(update_id=555))


async def test_admin_audit_log_is_append_only(database: Database) -> None:
    async with database.transaction() as session:
        entry = AdminAuditLog(admin_telegram_id=1, action="restrict_user", details={"ok": True})
        session.add(entry)

    async with rejected(database, "admin_audit_logs rows are append-only") as session:
        await session.execute(
            sa.update(AdminAuditLog).where(AdminAuditLog.id == entry.id).values(action="tampered")
        )

    async with database.transaction() as session:  # retention may still delete old rows
        await session.execute(sa.delete(AdminAuditLog).where(AdminAuditLog.id == entry.id))
    assert await scalar(database, "SELECT count(*) FROM admin_audit_logs") == 0
