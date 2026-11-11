"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``."""

from whisprlink.persistence.models.base import Base
from whisprlink.persistence.models.inbox import (
    InboxLink,
    InboxMessage,
    InboxOpenEvent,
    InboxThread,
    MessageDeliveryAttempt,
    MessageMediaItem,
)
from whisprlink.persistence.models.moderation import (
    AdminAuditLog,
    Block,
    ModerationAction,
    Report,
)
from whisprlink.persistence.models.platform import OutboxEvent, TelegramUpdateReceipt
from whisprlink.persistence.models.random_chat import RandomChatParticipant, RandomChatSession
from whisprlink.persistence.models.users import User, UserConsent, UserPreference

__all__ = [
    "AdminAuditLog",
    "Base",
    "Block",
    "InboxLink",
    "InboxMessage",
    "InboxOpenEvent",
    "InboxThread",
    "MessageDeliveryAttempt",
    "MessageMediaItem",
    "ModerationAction",
    "OutboxEvent",
    "RandomChatParticipant",
    "RandomChatSession",
    "Report",
    "TelegramUpdateReceipt",
    "User",
    "UserConsent",
    "UserPreference",
]
