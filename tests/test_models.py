"""Schema metadata tests that need no database."""

import sqlalchemy as sa

from whisprlink.persistence.models import Base

AGREED_TABLES = {
    "users",
    "user_consents",
    "inbox_links",
    "inbox_threads",
    "inbox_messages",
    "message_media_items",
    "message_delivery_attempts",
    "inbox_open_events",
    "random_chat_sessions",
    "random_chat_participants",
    "blocks",
    "reports",
    "moderation_actions",
    "outbox_events",
    "telegram_update_receipts",
    "user_preferences",
    "admin_audit_logs",
}


def test_metadata_contains_exactly_the_agreed_tables() -> None:
    assert set(Base.metadata.tables) == AGREED_TABLES


def test_every_table_has_a_primary_key() -> None:
    for table in Base.metadata.tables.values():
        assert table.primary_key.columns, table.name


def test_every_timestamp_column_is_timezone_aware() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.DateTime):
                assert column.type.timezone, f"{table.name}.{column.name}"


def test_all_constraints_and_indexes_are_explicitly_named() -> None:
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            assert constraint.name, f"unnamed constraint on {table.name}"
        for index in table.indexes:
            assert index.name, f"unnamed index on {table.name}"


def test_contact_and_location_sharing_default_to_off() -> None:
    columns = Base.metadata.tables["user_preferences"].columns

    for name in ("allow_contact_sharing", "allow_location_sharing"):
        assert str(columns[name].server_default.arg) == "false"  # type: ignore[union-attr]
