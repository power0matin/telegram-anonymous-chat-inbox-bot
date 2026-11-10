"""Enumerations persisted by the schema. Values are stable database contract strings."""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    BANNED = "banned"
    DELETED = "deleted"


class Language(StrEnum):
    FA = "fa"
    EN = "en"


class ConsentType(StrEnum):
    RULES = "rules"
    AGE_18_ATTESTATION = "age_18_attestation"


class InboxLinkStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ROTATED = "rotated"


class ParticipantRole(StrEnum):
    OWNER = "owner"
    SENDER = "sender"


class ThreadState(StrEnum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"


class ThreadCloser(StrEnum):
    OWNER = "owner"
    SENDER = "sender"
    SYSTEM = "system"


class MessageType(StrEnum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"
    ANIMATION = "animation"
    VIDEO_NOTE = "video_note"
    ALBUM = "album"
    CONTACT = "contact"
    LOCATION = "location"
    VENUE = "venue"
    POLL = "poll"


class MessageDeliveryState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DISCARDED = "discarded"


class DeliveryOutcome(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_PERMANENT = "failed_permanent"
    AMBIGUOUS = "ambiguous"


class RandomSessionState(StrEnum):
    SEARCHING = "searching"
    ACTIVE = "active"
    CLOSED = "closed"


class RandomEndReason(StrEnum):
    STOPPED = "stopped"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    PARTNER_UNAVAILABLE = "partner_unavailable"
    RESTRICTED = "restricted"
    STALE_RECOVERY = "stale_recovery"


class BlockScope(StrEnum):
    INBOX = "inbox"
    RANDOM_CHAT = "random_chat"


class ReportCategory(StrEnum):
    SPAM = "spam"
    HARASSMENT = "harassment"
    SEXUAL_CONTENT = "sexual_content"
    MINOR_SAFETY = "minor_safety"
    THREATS = "threats"
    SCAM = "scam"
    OTHER = "other"


class ReportStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ModerationActionType(StrEnum):
    RESTRICT = "restrict"
    UNRESTRICT = "unrestrict"
    BAN = "ban"
    UNBAN = "unban"


class OutboxState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UpdateReceiptStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
