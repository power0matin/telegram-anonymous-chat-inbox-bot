"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-09 22:45:50.378581+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIGGER_STATEMENTS = (
    # A thread can only be created through an active link, between unblocked participants.
    # FOR SHARE makes a concurrent link rotation/disable wait for this transaction.
    """
    CREATE FUNCTION whisprlink_guard_thread_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        link_status text;
    BEGIN
        SELECT status INTO link_status
        FROM inbox_links
        WHERE id = NEW.link_id AND owner_id = NEW.owner_id
        FOR SHARE;
        IF link_status IS DISTINCT FROM 'active' THEN
            RAISE EXCEPTION 'inbox link is not active'
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'inbox_thread_requires_active_link';
        END IF;
        IF EXISTS (
            SELECT 1 FROM blocks
            WHERE scope = 'inbox'
              AND ((blocker_id = NEW.owner_id AND blocked_id = NEW.sender_id)
                OR (blocker_id = NEW.sender_id AND blocked_id = NEW.owner_id))
        ) THEN
            RAISE EXCEPTION 'participants are blocked'
                USING ERRCODE = 'check_violation',
                      CONSTRAINT = 'inbox_thread_blocked_pair';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_inbox_threads_guard_insert
    BEFORE INSERT ON inbox_threads
    FOR EACH ROW EXECUTE FUNCTION whisprlink_guard_thread_insert()
    """,
    # Messages cannot be added to closed threads, to blocked pairs, or by the owner before the
    # initial message was opened.
    """
    CREATE FUNCTION whisprlink_guard_message_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        thread inbox_threads%ROWTYPE;
    BEGIN
        SELECT * INTO thread FROM inbox_threads WHERE id = NEW.thread_id FOR SHARE;
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;
        IF thread.state = 'closed' THEN
            RAISE EXCEPTION 'thread is closed'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'inbox_message_thread_closed';
        END IF;
        IF thread.state = 'pending' AND NEW.sender_role = 'owner' THEN
            RAISE EXCEPTION 'owner cannot reply before opening the thread'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'inbox_message_owner_before_open';
        END IF;
        IF EXISTS (
            SELECT 1 FROM blocks
            WHERE scope = 'inbox'
              AND ((blocker_id = thread.owner_id AND blocked_id = thread.sender_id)
                OR (blocker_id = thread.sender_id AND blocked_id = thread.owner_id))
        ) THEN
            RAISE EXCEPTION 'participants are blocked'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'inbox_message_blocked_pair';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_inbox_messages_guard_insert
    BEFORE INSERT ON inbox_messages
    FOR EACH ROW EXECUTE FUNCTION whisprlink_guard_message_insert()
    """,
    # Only the participant who is the message's recipient may open it.
    """
    CREATE FUNCTION whisprlink_guard_open_event() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        thread_owner bigint;
        thread_sender bigint;
        message_role text;
    BEGIN
        SELECT t.owner_id, t.sender_id, m.sender_role
        INTO thread_owner, thread_sender, message_role
        FROM inbox_messages m JOIN inbox_threads t ON t.id = m.thread_id
        WHERE m.id = NEW.message_id;
        IF NOT FOUND THEN
            RETURN NEW;
        END IF;
        IF (message_role = 'sender' AND NEW.opened_by_user_id <> thread_owner)
           OR (message_role = 'owner' AND NEW.opened_by_user_id <> thread_sender) THEN
            RAISE EXCEPTION 'only the message recipient can open it'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'inbox_open_by_recipient';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_inbox_open_events_guard_insert
    BEFORE INSERT ON inbox_open_events
    FOR EACH ROW EXECUTE FUNCTION whisprlink_guard_open_event()
    """,
    # Random chat participants must be active users, join open sessions, and not be blocked
    # against the person already in the session.
    """
    CREATE FUNCTION whisprlink_guard_random_participant() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM random_chat_sessions WHERE id = NEW.session_id AND state = 'closed'
        ) THEN
            RAISE EXCEPTION 'session is closed'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'random_participant_session_closed';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.user_id AND status = 'active') THEN
            RAISE EXCEPTION 'user is not eligible for random chat'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'random_participant_user_active';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM random_chat_participants p
            JOIN blocks b
              ON b.scope = 'random_chat'
             AND ((b.blocker_id = p.user_id AND b.blocked_id = NEW.user_id)
               OR (b.blocker_id = NEW.user_id AND b.blocked_id = p.user_id))
            WHERE p.session_id = NEW.session_id
        ) THEN
            RAISE EXCEPTION 'participants are blocked'
                USING ERRCODE = 'check_violation', CONSTRAINT = 'random_participant_blocked_pair';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_random_chat_participants_guard_insert
    BEFORE INSERT ON random_chat_participants
    FOR EACH ROW EXECUTE FUNCTION whisprlink_guard_random_participant()
    """,
    # Closing a session always releases its participants so a user can never stay "busy".
    """
    CREATE FUNCTION whisprlink_release_participants_on_close() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        UPDATE random_chat_participants
        SET left_at = COALESCE(NEW.ended_at, now()), left_reason = NEW.end_reason
        WHERE session_id = NEW.id AND left_at IS NULL;
        RETURN NULL;
    END $$
    """,
    """
    CREATE TRIGGER trg_random_chat_sessions_release_participants
    AFTER UPDATE OF state ON random_chat_sessions
    FOR EACH ROW WHEN (NEW.state = 'closed' AND OLD.state <> 'closed')
    EXECUTE FUNCTION whisprlink_release_participants_on_close()
    """,
    # The admin audit log is append-only (retention may delete old rows, never edit them).
    """
    CREATE FUNCTION whisprlink_reject_update() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION '% rows are append-only', TG_TABLE_NAME
            USING ERRCODE = 'check_violation', CONSTRAINT = 'append_only';
    END $$
    """,
    """
    CREATE TRIGGER trg_admin_audit_logs_append_only
    BEFORE UPDATE ON admin_audit_logs
    FOR EACH ROW EXECUTE FUNCTION whisprlink_reject_update()
    """,
)

_DROP_TRIGGER_STATEMENTS = (
    "DROP TRIGGER IF EXISTS trg_admin_audit_logs_append_only ON admin_audit_logs",
    "DROP FUNCTION IF EXISTS whisprlink_reject_update()",
    "DROP TRIGGER IF EXISTS trg_random_chat_sessions_release_participants ON random_chat_sessions",
    "DROP FUNCTION IF EXISTS whisprlink_release_participants_on_close()",
    "DROP TRIGGER IF EXISTS trg_random_chat_participants_guard_insert ON random_chat_participants",
    "DROP FUNCTION IF EXISTS whisprlink_guard_random_participant()",
    "DROP TRIGGER IF EXISTS trg_inbox_open_events_guard_insert ON inbox_open_events",
    "DROP FUNCTION IF EXISTS whisprlink_guard_open_event()",
    "DROP TRIGGER IF EXISTS trg_inbox_messages_guard_insert ON inbox_messages",
    "DROP FUNCTION IF EXISTS whisprlink_guard_message_insert()",
    "DROP TRIGGER IF EXISTS trg_inbox_threads_guard_insert ON inbox_threads",
    "DROP FUNCTION IF EXISTS whisprlink_guard_thread_insert()",
)


def _create_integrity_triggers() -> None:
    for statement in _TRIGGER_STATEMENTS:
        op.execute(statement)


def _drop_integrity_triggers() -> None:
    for statement in _DROP_TRIGGER_STATEMENTS:
        op.execute(statement)


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_logs")),
    )
    op.create_index(
        "ix_admin_audit_logs_admin_created",
        "admin_audit_logs",
        ["admin_telegram_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"], unique=False
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="outbox_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state <> 'processing' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name=op.f("ck_outbox_events_processing_requires_lease"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_outbox_events_attempts_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency_key"),
    )
    op.create_index(
        "ix_outbox_events_pending_next_attempt",
        "outbox_events",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.create_index(
        "ix_outbox_events_processing_lease",
        "outbox_events",
        ["lease_expires_at"],
        unique=False,
        postgresql_where=sa.text("state = 'processing'"),
    )
    op.create_table(
        "random_chat_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "public_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "state",
            sa.Enum(
                "searching",
                "active",
                "closed",
                name="random_session_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="searching",
            nullable=False,
        ),
        sa.Column(
            "end_reason",
            sa.Enum(
                "stopped",
                "skipped",
                "cancelled",
                "partner_unavailable",
                "restricted",
                "stale_recovery",
                name="random_end_reason",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(state = 'closed') = (end_reason IS NOT NULL)",
            name=op.f("ck_random_chat_sessions_closed_iff_end_reason"),
        ),
        sa.CheckConstraint(
            "(state = 'closed') = (ended_at IS NOT NULL)",
            name=op.f("ck_random_chat_sessions_closed_iff_ended_at"),
        ),
        sa.CheckConstraint(
            "(state = 'searching') = (started_at IS NULL) OR state = 'closed'",
            name=op.f("ck_random_chat_sessions_started_iff_matched"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_random_chat_sessions")),
        sa.UniqueConstraint("public_id", name="uq_random_chat_sessions_public_id"),
    )
    op.create_index(
        "ix_random_chat_sessions_state_created_at",
        "random_chat_sessions",
        ["state", "created_at"],
        unique=False,
    )
    op.create_table(
        "telegram_update_receipts",
        sa.Column("update_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "received",
                "processed",
                "failed",
                name="update_receipt_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="received",
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("update_id", name=op.f("pk_telegram_update_receipts")),
    )
    op.create_index(
        "ix_telegram_update_receipts_received_at",
        "telegram_update_receipts",
        ["received_at"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "restricted",
                "banned",
                "deleted",
                name="user_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("restricted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'deleted') = (deleted_at IS NOT NULL)",
            name=op.f("ck_users_deleted_iff_deleted_at"),
        ),
        sa.CheckConstraint(
            "(status = 'deleted') = (telegram_user_id IS NULL)",
            name=op.f("ck_users_deleted_iff_no_telegram_id"),
        ),
        sa.CheckConstraint("telegram_user_id > 0", name=op.f("ck_users_telegram_user_id_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
    )
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"], unique=False)
    op.create_index("ix_users_status", "users", ["status"], unique=False)
    op.create_table(
        "blocks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("blocker_id", sa.BigInteger(), nullable=False),
        sa.Column("blocked_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "scope",
            sa.Enum(
                "inbox",
                "random_chat",
                name="block_scope",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("blocker_id <> blocked_id", name=op.f("ck_blocks_no_self_block")),
        sa.ForeignKeyConstraint(
            ["blocked_id"],
            ["users.id"],
            name=op.f("fk_blocks_blocked_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["blocker_id"],
            ["users.id"],
            name=op.f("fk_blocks_blocker_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocks")),
        sa.UniqueConstraint("blocker_id", "blocked_id", "scope", name="uq_blocks_pair_scope"),
    )
    op.create_index("ix_blocks_blocked_id", "blocks", ["blocked_id"], unique=False)
    op.create_table(
        "inbox_links",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "paused",
                "disabled",
                "rotated",
                name="inbox_link_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_inbox_links_token_hash_length")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_inbox_links_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox_links")),
        sa.UniqueConstraint("id", "owner_id", name="uq_inbox_links_id_owner_id"),
        sa.UniqueConstraint("token_hash", name="uq_inbox_links_token_hash"),
    )
    op.create_index(
        "uq_inbox_links_one_live_link_per_owner",
        "inbox_links",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'paused')"),
    )
    op.create_table(
        "random_chat_participants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "left_reason",
            sa.Enum(
                "stopped",
                "skipped",
                "cancelled",
                "partner_unavailable",
                "restricted",
                "stale_recovery",
                name="participant_left_reason",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(left_at IS NULL) = (left_reason IS NULL)",
            name=op.f("ck_random_chat_participants_left_at_matches_left_reason"),
        ),
        sa.CheckConstraint("slot IN (1, 2)", name=op.f("ck_random_chat_participants_slot_range")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["random_chat_sessions.id"],
            name=op.f("fk_random_chat_participants_session_id_random_chat_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_random_chat_participants_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_random_chat_participants")),
        sa.UniqueConstraint("session_id", "slot", name="uq_random_chat_participants_slot"),
        sa.UniqueConstraint("session_id", "user_id", name="uq_random_chat_participants_user"),
    )
    op.create_index(
        "uq_random_chat_participants_one_active_membership",
        "random_chat_participants",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.create_table(
        "user_consents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "consent_type",
            sa.Enum(
                "rules",
                "age_18_attestation",
                name="consent_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_consents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_consents")),
        sa.UniqueConstraint(
            "user_id", "consent_type", "version", name="uq_user_consents_user_type_version"
        ),
    )
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "language",
            sa.Enum(
                "fa", "en", name="language", native_enum=False, create_constraint=True, length=32
            ),
            server_default="en",
            nullable=False,
        ),
        sa.Column(
            "random_chat_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "notifications_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "allow_contact_sharing", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "allow_location_sharing", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_preferences")),
    )
    op.create_table(
        "inbox_threads",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "public_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "pending",
                "open",
                "closed",
                name="thread_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "closed_by",
            sa.Enum(
                "owner",
                "sender",
                "system",
                name="thread_closer",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state = 'closed') = (closed_at IS NOT NULL)",
            name=op.f("ck_inbox_threads_closed_iff_closed_at"),
        ),
        sa.CheckConstraint(
            "(state = 'closed') = (closed_by IS NOT NULL)",
            name=op.f("ck_inbox_threads_closed_iff_closed_by"),
        ),
        sa.CheckConstraint(
            "owner_id <> sender_id", name=op.f("ck_inbox_threads_owner_differs_from_sender")
        ),
        sa.ForeignKeyConstraint(
            ["link_id", "owner_id"],
            ["inbox_links.id", "inbox_links.owner_id"],
            name="fk_inbox_threads_link_owner_inbox_links",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_inbox_threads_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_inbox_threads_sender_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox_threads")),
        sa.UniqueConstraint("id", "owner_id", name="uq_inbox_threads_id_owner_id"),
        sa.UniqueConstraint("id", "sender_id", name="uq_inbox_threads_id_sender_id"),
        sa.UniqueConstraint("public_id", name="uq_inbox_threads_public_id"),
    )
    op.create_index(
        "ix_inbox_threads_owner_state_activity",
        "inbox_threads",
        ["owner_id", "state", "last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_inbox_threads_sender_state_activity",
        "inbox_threads",
        ["sender_id", "state", "last_activity_at"],
        unique=False,
    )
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "sender_role",
            sa.Enum(
                "owner",
                "sender",
                name="participant_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "message_type",
            sa.Enum(
                "text",
                "photo",
                "video",
                "audio",
                "voice",
                "document",
                "sticker",
                "animation",
                "video_note",
                "album",
                "contact",
                "location",
                "venue",
                "poll",
                name="message_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("media_group_id", sa.String(length=64), nullable=True),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "delivery_state",
            sa.Enum(
                "pending",
                "delivered",
                "failed",
                "discarded",
                name="message_delivery_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reply_to_message_id IS NULL OR reply_to_message_id <> id",
            name=op.f("ck_inbox_messages_reply_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id", "reply_to_message_id"],
            ["inbox_messages.thread_id", "inbox_messages.id"],
            name="fk_inbox_messages_reply_target_same_thread",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["inbox_threads.id"],
            name=op.f("fk_inbox_messages_thread_id_inbox_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox_messages")),
        sa.UniqueConstraint(
            "source_chat_id", "source_message_id", name="uq_inbox_messages_source_message"
        ),
        sa.UniqueConstraint("thread_id", "id", name="uq_inbox_messages_thread_id_id"),
    )
    op.create_index(
        "ix_inbox_messages_thread_created_id",
        "inbox_messages",
        ["thread_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "message_delivery_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "pending",
                "delivered",
                "failed_transient",
                "failed_permanent",
                "ambiguous",
                name="delivery_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("telegram_error_code", sa.SmallInteger(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(outcome = 'pending') = (finished_at IS NULL)",
            name=op.f("ck_message_delivery_attempts_finished_iff_not_pending"),
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name=op.f("ck_message_delivery_attempts_attempt_number_positive")
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["inbox_messages.id"],
            name=op.f("fk_message_delivery_attempts_message_id_inbox_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_message_delivery_attempts_recipient_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_delivery_attempts")),
        sa.UniqueConstraint(
            "id", "message_id", "outcome", name="uq_message_delivery_attempts_id_message_outcome"
        ),
        sa.UniqueConstraint(
            "message_id",
            "recipient_user_id",
            "attempt_number",
            name="uq_message_delivery_attempts_sequence",
        ),
    )
    op.create_index(
        "ix_message_delivery_attempts_message_id",
        "message_delivery_attempts",
        ["message_id"],
        unique=False,
    )
    op.create_table(
        "message_media_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum(
                "text",
                "photo",
                "video",
                "audio",
                "voice",
                "document",
                "sticker",
                "animation",
                "video_note",
                "album",
                "contact",
                "location",
                "venue",
                "poll",
                name="media_item_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=True),
        sa.Column("file_unique_id", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_message_media_items_position_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["inbox_messages.id"],
            name=op.f("fk_message_media_items_message_id_inbox_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_media_items")),
        sa.UniqueConstraint("message_id", "position", name="uq_message_media_items_position"),
        sa.UniqueConstraint(
            "source_chat_id", "source_message_id", name="uq_message_media_items_source_message"
        ),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("reporter_id", sa.BigInteger(), nullable=False),
        sa.Column("reported_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "spam",
                "harassment",
                "sexual_content",
                "minor_safety",
                "threats",
                "scam",
                "other",
                name="report_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "in_review",
                "resolved",
                "dismissed",
                name="report_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("explanation", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_admin_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("resolution_note", sa.String(length=1000), nullable=True),
        sa.CheckConstraint(
            "(status IN ('resolved', 'dismissed')) = (resolved_at IS NOT NULL)",
            name=op.f("ck_reports_resolved_iff_resolved_at"),
        ),
        sa.CheckConstraint("reporter_id <> reported_id", name=op.f("ck_reports_no_self_report")),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["inbox_messages.id"],
            name=op.f("fk_reports_message_id_inbox_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reported_id"],
            ["users.id"],
            name=op.f("fk_reports_reported_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name=op.f("fk_reports_reporter_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["random_chat_sessions.id"],
            name=op.f("fk_reports_session_id_random_chat_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["inbox_threads.id"],
            name=op.f("fk_reports_thread_id_inbox_threads"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index("ix_reports_reported_id", "reports", ["reported_id"], unique=False)
    op.create_index(
        "ix_reports_status_created_at", "reports", ["status", "created_at"], unique=False
    )
    op.create_table(
        "inbox_open_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("opened_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("delivery_attempt_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "attempt_outcome",
            sa.Enum(
                "pending",
                "delivered",
                "failed_transient",
                "failed_permanent",
                "ambiguous",
                name="open_attempt_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="delivered",
            nullable=False,
        ),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "attempt_outcome = 'delivered'",
            name=op.f("ck_inbox_open_events_requires_delivered_attempt"),
        ),
        sa.ForeignKeyConstraint(
            ["delivery_attempt_id", "message_id", "attempt_outcome"],
            [
                "message_delivery_attempts.id",
                "message_delivery_attempts.message_id",
                "message_delivery_attempts.outcome",
            ],
            name="fk_inbox_open_events_delivered_attempt",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_user_id"],
            ["users.id"],
            name=op.f("fk_inbox_open_events_opened_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id", "message_id"],
            ["inbox_messages.thread_id", "inbox_messages.id"],
            name="fk_inbox_open_events_thread_message_inbox_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox_open_events")),
        sa.UniqueConstraint("message_id", name="uq_inbox_open_events_message_id"),
    )
    op.create_table(
        "moderation_actions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "restrict",
                "unrestrict",
                "ban",
                "unban",
                name="moderation_action_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("report_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["reports.id"],
            name=op.f("fk_moderation_actions_report_id_reports"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_moderation_actions_target_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moderation_actions")),
    )
    op.create_index(
        "ix_moderation_actions_target_created",
        "moderation_actions",
        ["target_user_id", "created_at"],
        unique=False,
    )
    _create_integrity_triggers()


def downgrade() -> None:
    _drop_integrity_triggers()
    op.drop_index("ix_moderation_actions_target_created", table_name="moderation_actions")
    op.drop_table("moderation_actions")
    op.drop_table("inbox_open_events")
    op.drop_index("ix_reports_status_created_at", table_name="reports")
    op.drop_index("ix_reports_reported_id", table_name="reports")
    op.drop_table("reports")
    op.drop_table("message_media_items")
    op.drop_index("ix_message_delivery_attempts_message_id", table_name="message_delivery_attempts")
    op.drop_table("message_delivery_attempts")
    op.drop_index("ix_inbox_messages_thread_created_id", table_name="inbox_messages")
    op.drop_table("inbox_messages")
    op.drop_index("ix_inbox_threads_sender_state_activity", table_name="inbox_threads")
    op.drop_index("ix_inbox_threads_owner_state_activity", table_name="inbox_threads")
    op.drop_table("inbox_threads")
    op.drop_table("user_preferences")
    op.drop_table("user_consents")
    op.drop_index(
        "uq_random_chat_participants_one_active_membership",
        table_name="random_chat_participants",
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.drop_table("random_chat_participants")
    op.drop_index(
        "uq_inbox_links_one_live_link_per_owner",
        table_name="inbox_links",
        postgresql_where=sa.text("status IN ('active', 'paused')"),
    )
    op.drop_table("inbox_links")
    op.drop_index("ix_blocks_blocked_id", table_name="blocks")
    op.drop_table("blocks")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_telegram_update_receipts_received_at", table_name="telegram_update_receipts")
    op.drop_table("telegram_update_receipts")
    op.drop_index("ix_random_chat_sessions_state_created_at", table_name="random_chat_sessions")
    op.drop_table("random_chat_sessions")
    op.drop_index(
        "ix_outbox_events_processing_lease",
        table_name="outbox_events",
        postgresql_where=sa.text("state = 'processing'"),
    )
    op.drop_index(
        "ix_outbox_events_pending_next_attempt",
        table_name="outbox_events",
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.drop_table("outbox_events")
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_created", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
