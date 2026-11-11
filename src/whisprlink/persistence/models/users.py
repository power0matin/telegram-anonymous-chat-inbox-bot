"""Users, consents, and preferences."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from whisprlink.persistence.models.base import Base, enum_type
from whisprlink.persistence.models.enums import ConsentType, Language, UserStatus


class User(Base):
    """A Telegram user known to the bot.

    ``telegram_user_id`` is internal routing data. Account deletion tombstones the row:
    status becomes ``deleted`` and the Telegram ID is cleared, which keeps foreign keys
    valid without retaining the identifier.
    """

    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("telegram_user_id > 0", name="telegram_user_id_positive"),
        sa.CheckConstraint(
            "(status = 'deleted') = (telegram_user_id IS NULL)",
            name="deleted_iff_no_telegram_id",
        ),
        sa.CheckConstraint(
            "(status = 'deleted') = (deleted_at IS NOT NULL)", name="deleted_iff_deleted_at"
        ),
        sa.UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        sa.Index("ix_users_status", "status"),
        sa.Index("ix_users_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, "user_status"),
        server_default=UserStatus.ACTIVE.value,
    )
    restricted_until: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    last_seen_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]


class UserConsent(Base):
    """Versioned acceptance of rules and the 18+ self-attestation."""

    __tablename__ = "user_consents"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "consent_type", "version", name="uq_user_consents_user_type_version"
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    consent_type: Mapped[ConsentType] = mapped_column(enum_type(ConsentType, "consent_type"))
    version: Mapped[str] = mapped_column(sa.String(32))
    accepted_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class UserPreference(Base):
    """Per-user settings. Contact and location sharing are opt-in and default to off."""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[Language] = mapped_column(
        enum_type(Language, "language"), server_default=Language.EN.value
    )
    random_chat_enabled: Mapped[bool] = mapped_column(server_default=sa.true())
    notifications_enabled: Mapped[bool] = mapped_column(server_default=sa.true())
    allow_contact_sharing: Mapped[bool] = mapped_column(server_default=sa.false())
    allow_location_sharing: Mapped[bool] = mapped_column(server_default=sa.false())
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
