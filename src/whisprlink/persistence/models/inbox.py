"""Personal inbox: links, threads, messages, media references, delivery, and open receipts.

Message bodies are never stored. Content is relayed with Telegram server-side references
(``source_chat_id`` / ``source_message_id`` and file identifiers).
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from whisprlink.persistence.models.base import Base, enum_type
from whisprlink.persistence.models.enums import (
    DeliveryOutcome,
    InboxLinkStatus,
    MessageDeliveryState,
    MessageType,
    ParticipantRole,
    ThreadCloser,
    ThreadState,
)


class InboxLink(Base):
    """A personal deep-link token, stored only as a 32-byte keyed hash."""

    __tablename__ = "inbox_links"
    __table_args__ = (
        sa.CheckConstraint("octet_length(token_hash) = 32", name="token_hash_length"),
        sa.UniqueConstraint("token_hash", name="uq_inbox_links_token_hash"),
        sa.UniqueConstraint("id", "owner_id", name="uq_inbox_links_id_owner_id"),
        sa.Index(
            "uq_inbox_links_one_live_link_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=sa.text("status IN ('active', 'paused')"),
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    token_hash: Mapped[bytes] = mapped_column(sa.LargeBinary)
    status: Mapped[InboxLinkStatus] = mapped_column(
        enum_type(InboxLinkStatus, "inbox_link_status"),
        server_default=InboxLinkStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    status_changed_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class InboxThread(Base):
    """One conversation between exactly one owner and one anonymous sender."""

    __tablename__ = "inbox_threads"
    __table_args__ = (
        sa.CheckConstraint("owner_id <> sender_id", name="owner_differs_from_sender"),
        sa.CheckConstraint(
            "(state = 'closed') = (closed_at IS NOT NULL)", name="closed_iff_closed_at"
        ),
        sa.CheckConstraint(
            "(state = 'closed') = (closed_by IS NOT NULL)", name="closed_iff_closed_by"
        ),
        sa.UniqueConstraint("public_id", name="uq_inbox_threads_public_id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_inbox_threads_id_owner_id"),
        sa.UniqueConstraint("id", "sender_id", name="uq_inbox_threads_id_sender_id"),
        sa.ForeignKeyConstraint(
            ["link_id", "owner_id"],
            ["inbox_links.id", "inbox_links.owner_id"],
            name="fk_inbox_threads_link_owner_inbox_links",
            ondelete="RESTRICT",
        ),
        sa.Index("ix_inbox_threads_owner_state_activity", "owner_id", "state", "last_activity_at"),
        sa.Index(
            "ix_inbox_threads_sender_state_activity", "sender_id", "state", "last_activity_at"
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(server_default=sa.text("gen_random_uuid()"))
    link_id: Mapped[int] = mapped_column(sa.BigInteger)
    owner_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    sender_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    state: Mapped[ThreadState] = mapped_column(
        enum_type(ThreadState, "thread_state"), server_default=ThreadState.PENDING.value
    )
    closed_by: Mapped[ThreadCloser | None] = mapped_column(enum_type(ThreadCloser, "thread_closer"))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    opened_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    last_activity_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class InboxMessage(Base):
    """A logical message (single item or album) in a thread's chronological timeline."""

    __tablename__ = "inbox_messages"
    __table_args__ = (
        sa.UniqueConstraint("thread_id", "id", name="uq_inbox_messages_thread_id_id"),
        sa.UniqueConstraint(
            "source_chat_id", "source_message_id", name="uq_inbox_messages_source_message"
        ),
        sa.ForeignKeyConstraint(
            ["thread_id", "reply_to_message_id"],
            ["inbox_messages.thread_id", "inbox_messages.id"],
            name="fk_inbox_messages_reply_target_same_thread",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "reply_to_message_id IS NULL OR reply_to_message_id <> id",
            name="reply_not_self",
        ),
        sa.Index("ix_inbox_messages_thread_created_id", "thread_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    thread_id: Mapped[int] = mapped_column(sa.ForeignKey("inbox_threads.id", ondelete="CASCADE"))
    sender_role: Mapped[ParticipantRole] = mapped_column(
        enum_type(ParticipantRole, "participant_role")
    )
    reply_to_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    message_type: Mapped[MessageType] = mapped_column(enum_type(MessageType, "message_type"))
    media_group_id: Mapped[str | None] = mapped_column(sa.String(64))
    source_chat_id: Mapped[int] = mapped_column(sa.BigInteger)
    source_message_id: Mapped[int] = mapped_column(sa.BigInteger)
    delivery_state: Mapped[MessageDeliveryState] = mapped_column(
        enum_type(MessageDeliveryState, "message_delivery_state"),
        server_default=MessageDeliveryState.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    delivered_at: Mapped[datetime | None]


class MessageMediaItem(Base):
    """Ordered Telegram media reference belonging to a message (one per album item)."""

    __tablename__ = "message_media_items"
    __table_args__ = (
        sa.CheckConstraint("position >= 0", name="position_non_negative"),
        sa.UniqueConstraint("message_id", "position", name="uq_message_media_items_position"),
        sa.UniqueConstraint(
            "source_chat_id", "source_message_id", name="uq_message_media_items_source_message"
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    message_id: Mapped[int] = mapped_column(sa.ForeignKey("inbox_messages.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(sa.SmallInteger)
    media_type: Mapped[MessageType] = mapped_column(enum_type(MessageType, "media_item_type"))
    source_chat_id: Mapped[int] = mapped_column(sa.BigInteger)
    source_message_id: Mapped[int] = mapped_column(sa.BigInteger)
    file_id: Mapped[str | None] = mapped_column(sa.String(255))
    file_unique_id: Mapped[str | None] = mapped_column(sa.String(64))
    file_size: Mapped[int | None] = mapped_column(sa.BigInteger)
    mime_type: Mapped[str | None] = mapped_column(sa.String(128))


class MessageDeliveryAttempt(Base):
    """Append-style record of each attempt to deliver a message to its recipient."""

    __tablename__ = "message_delivery_attempts"
    __table_args__ = (
        sa.CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        sa.CheckConstraint(
            "(outcome = 'pending') = (finished_at IS NULL)", name="finished_iff_not_pending"
        ),
        sa.UniqueConstraint(
            "message_id",
            "recipient_user_id",
            "attempt_number",
            name="uq_message_delivery_attempts_sequence",
        ),
        sa.UniqueConstraint(
            "id", "message_id", "outcome", name="uq_message_delivery_attempts_id_message_outcome"
        ),
        sa.Index("ix_message_delivery_attempts_message_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    message_id: Mapped[int] = mapped_column(sa.ForeignKey("inbox_messages.id", ondelete="CASCADE"))
    recipient_user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    attempt_number: Mapped[int] = mapped_column(sa.SmallInteger)
    outcome: Mapped[DeliveryOutcome] = mapped_column(
        enum_type(DeliveryOutcome, "delivery_outcome"),
        server_default=DeliveryOutcome.PENDING.value,
    )
    error_category: Mapped[str | None] = mapped_column(sa.String(64))
    telegram_error_code: Mapped[int | None] = mapped_column(sa.SmallInteger)
    started_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    finished_at: Mapped[datetime | None]


class InboxOpenEvent(Base):
    """Application-level receipt that a recipient explicitly opened a message.

    The composite foreign key pins the event to a delivery attempt of the same message whose
    outcome is ``delivered``; a receipt therefore cannot exist without successful delivery.
    """

    __tablename__ = "inbox_open_events"
    __table_args__ = (
        sa.CheckConstraint("attempt_outcome = 'delivered'", name="requires_delivered_attempt"),
        sa.UniqueConstraint("message_id", name="uq_inbox_open_events_message_id"),
        sa.ForeignKeyConstraint(
            ["thread_id", "message_id"],
            ["inbox_messages.thread_id", "inbox_messages.id"],
            name="fk_inbox_open_events_thread_message_inbox_messages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_attempt_id", "message_id", "attempt_outcome"],
            [
                "message_delivery_attempts.id",
                "message_delivery_attempts.message_id",
                "message_delivery_attempts.outcome",
            ],
            name="fk_inbox_open_events_delivered_attempt",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    thread_id: Mapped[int] = mapped_column(sa.BigInteger)
    message_id: Mapped[int] = mapped_column(sa.BigInteger)
    opened_by_user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    delivery_attempt_id: Mapped[int] = mapped_column(sa.BigInteger)
    attempt_outcome: Mapped[DeliveryOutcome] = mapped_column(
        enum_type(DeliveryOutcome, "open_attempt_outcome"),
        server_default=DeliveryOutcome.DELIVERED.value,
    )
    opened_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
