"""Blocks, reports, moderation actions, and the admin audit log."""

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from whisprlink.persistence.models.base import Base, enum_type
from whisprlink.persistence.models.enums import (
    BlockScope,
    ModerationActionType,
    ReportCategory,
    ReportStatus,
)


class Block(Base):
    """``blocker_id`` blocked ``blocked_id``; enforced in both directions for new messages."""

    __tablename__ = "blocks"
    __table_args__ = (
        sa.CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),
        sa.UniqueConstraint("blocker_id", "blocked_id", "scope", name="uq_blocks_pair_scope"),
        sa.Index("ix_blocks_blocked_id", "blocked_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    blocker_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    blocked_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    scope: Mapped[BlockScope] = mapped_column(enum_type(BlockScope, "block_scope"))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class Report(Base):
    """A user report. The reporter's identity must never be shown to the reported user."""

    __tablename__ = "reports"
    __table_args__ = (
        sa.CheckConstraint("reporter_id <> reported_id", name="no_self_report"),
        sa.CheckConstraint(
            "(status IN ('resolved', 'dismissed')) = (resolved_at IS NOT NULL)",
            name="resolved_iff_resolved_at",
        ),
        sa.Index("ix_reports_status_created_at", "status", "created_at"),
        sa.Index("ix_reports_reported_id", "reported_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    reporter_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    reported_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    thread_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("inbox_threads.id", ondelete="SET NULL")
    )
    message_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("inbox_messages.id", ondelete="SET NULL")
    )
    session_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("random_chat_sessions.id", ondelete="SET NULL")
    )
    category: Mapped[ReportCategory] = mapped_column(enum_type(ReportCategory, "report_category"))
    status: Mapped[ReportStatus] = mapped_column(
        enum_type(ReportStatus, "report_status"), server_default=ReportStatus.PENDING.value
    )
    explanation: Mapped[str | None] = mapped_column(sa.String(1000))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    resolved_at: Mapped[datetime | None]
    resolved_by_admin_telegram_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    resolution_note: Mapped[str | None] = mapped_column(sa.String(1000))


class ModerationAction(Base):
    """A restriction, ban, or their reversal applied by an authorized admin."""

    __tablename__ = "moderation_actions"
    __table_args__ = (
        sa.Index("ix_moderation_actions_target_created", "target_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    target_user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    admin_telegram_id: Mapped[int] = mapped_column(sa.BigInteger)
    action: Mapped[ModerationActionType] = mapped_column(
        enum_type(ModerationActionType, "moderation_action_type")
    )
    reason: Mapped[str | None] = mapped_column(sa.String(500))
    report_id: Mapped[int | None] = mapped_column(sa.ForeignKey("reports.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class AdminAuditLog(Base):
    """Append-only record of privileged actions; updates are rejected by a trigger."""

    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        sa.Index("ix_admin_audit_logs_created_at", "created_at"),
        sa.Index("ix_admin_audit_logs_admin_created", "admin_telegram_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(sa.BigInteger)
    action: Mapped[str] = mapped_column(sa.String(64))
    target_type: Mapped[str | None] = mapped_column(sa.String(32))
    target_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    details: Mapped[dict[str, Any]] = mapped_column(server_default=sa.text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
