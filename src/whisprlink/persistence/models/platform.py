"""Delivery outbox and Telegram update deduplication."""

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from whisprlink.persistence.models.base import Base, enum_type
from whisprlink.persistence.models.enums import OutboxState, UpdateReceiptStatus


class OutboxEvent(Base):
    """Durable side-effect request written in the same transaction as the domain change."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.CheckConstraint(
            "state <> 'processing' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="processing_requires_lease",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency_key"),
        sa.Index(
            "ix_outbox_events_pending_next_attempt",
            "next_attempt_at",
            postgresql_where=sa.text("state = 'pending'"),
        ),
        sa.Index(
            "ix_outbox_events_processing_lease",
            "lease_expires_at",
            postgresql_where=sa.text("state = 'processing'"),
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    event_type: Mapped[str] = mapped_column(sa.String(64))
    aggregate_type: Mapped[str] = mapped_column(sa.String(32))
    aggregate_id: Mapped[int] = mapped_column(sa.BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(server_default=sa.text("'{}'::jsonb"))
    idempotency_key: Mapped[str] = mapped_column(sa.String(128))
    state: Mapped[OutboxState] = mapped_column(
        enum_type(OutboxState, "outbox_state"), server_default=OutboxState.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(sa.SmallInteger, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    lease_owner: Mapped[str | None] = mapped_column(sa.String(64))
    lease_expires_at: Mapped[datetime | None]
    last_error_category: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    completed_at: Mapped[datetime | None]


class TelegramUpdateReceipt(Base):
    """Primary-key uniqueness on ``update_id`` makes duplicate updates detectable."""

    __tablename__ = "telegram_update_receipts"
    __table_args__ = (sa.Index("ix_telegram_update_receipts_received_at", "received_at"),)

    update_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=False)
    status: Mapped[UpdateReceiptStatus] = mapped_column(
        enum_type(UpdateReceiptStatus, "update_receipt_status"),
        server_default=UpdateReceiptStatus.RECEIVED.value,
    )
    received_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    processed_at: Mapped[datetime | None]
