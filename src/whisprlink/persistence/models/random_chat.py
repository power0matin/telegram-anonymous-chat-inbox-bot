"""Random one-to-one chat sessions and membership."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from whisprlink.persistence.models.base import Base, enum_type
from whisprlink.persistence.models.enums import RandomEndReason, RandomSessionState


class RandomChatSession(Base):
    """A matching/chat session: ``searching`` (one participant), ``active`` (two), ``closed``."""

    __tablename__ = "random_chat_sessions"
    __table_args__ = (
        sa.CheckConstraint(
            "(state = 'closed') = (ended_at IS NOT NULL)", name="closed_iff_ended_at"
        ),
        sa.CheckConstraint(
            "(state = 'closed') = (end_reason IS NOT NULL)", name="closed_iff_end_reason"
        ),
        sa.CheckConstraint(
            "(state = 'searching') = (started_at IS NULL) OR state = 'closed'",
            name="started_iff_matched",
        ),
        sa.UniqueConstraint("public_id", name="uq_random_chat_sessions_public_id"),
        sa.Index("ix_random_chat_sessions_state_created_at", "state", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(server_default=sa.text("gen_random_uuid()"))
    state: Mapped[RandomSessionState] = mapped_column(
        enum_type(RandomSessionState, "random_session_state"),
        server_default=RandomSessionState.SEARCHING.value,
    )
    end_reason: Mapped[RandomEndReason | None] = mapped_column(
        enum_type(RandomEndReason, "random_end_reason")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]


class RandomChatParticipant(Base):
    """A user's membership in a session.

    A partial unique index allows at most one membership with ``left_at IS NULL`` per user,
    and ``slot`` limits a session to two distinct participants.
    """

    __tablename__ = "random_chat_participants"
    __table_args__ = (
        sa.CheckConstraint("slot IN (1, 2)", name="slot_range"),
        sa.CheckConstraint(
            "(left_at IS NULL) = (left_reason IS NULL)", name="left_at_matches_left_reason"
        ),
        sa.UniqueConstraint("session_id", "slot", name="uq_random_chat_participants_slot"),
        sa.UniqueConstraint("session_id", "user_id", name="uq_random_chat_participants_user"),
        sa.Index(
            "uq_random_chat_participants_one_active_membership",
            "user_id",
            unique=True,
            postgresql_where=sa.text("left_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        sa.ForeignKey("random_chat_sessions.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    slot: Mapped[int] = mapped_column(sa.SmallInteger)
    joined_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    left_at: Mapped[datetime | None]
    left_reason: Mapped[RandomEndReason | None] = mapped_column(
        enum_type(RandomEndReason, "participant_left_reason")
    )
