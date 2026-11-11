"""Structured logging with secret and content redaction."""

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO

import structlog

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "database_url",
    "redis_url",
    "authorization",
)
_SENSITIVE_EXACT_KEYS = frozenset({"text", "caption", "body", "message_text", "message_body"})
_BOT_TOKEN_PATTERN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
_URL_CREDENTIALS_PATTERN = re.compile(r"(\w+://[^:/\s@]+:)[^@/\s]+(@)")


def _scrub_string(value: str) -> str:
    value = _BOT_TOKEN_PATTERN.sub(REDACTED, value)
    return _URL_CREDENTIALS_PATTERN.sub(rf"\1{REDACTED}\2", value)


def _is_sensitive_key(key: object) -> bool:
    lowered = str(key).lower()
    return lowered in _SENSITIVE_EXACT_KEYS or any(
        part in lowered for part in _SENSITIVE_KEY_PARTS
    )


def _redact_value(value: Any) -> Any:
    """Redact nested structures as well as plain strings (including formatted tracebacks)."""
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, MutableMapping):
        for nested_key, nested_value in list(value.items()):
            value[nested_key] = (
                REDACTED if _is_sensitive_key(nested_key) else _redact_value(nested_value)
            )
        return value
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Mask sensitive keys and credential-shaped substrings before rendering."""
    for key, value in list(event_dict.items()):
        event_dict[key] = REDACTED if _is_sensitive_key(key) else _redact_value(value)
    return event_dict


def configure_logging(
    level: str = "INFO", log_format: str = "console", *, stream: TextIO | None = None
) -> None:
    """Route structlog and standard-library logging through one redacting formatter."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redact_sensitive,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            # Exception formatting happens after the first structlog pass. Redact again here,
            # including nested traceback fields, before anything reaches the output handler.
            redact_sensitive,
            renderer,
        ],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # Never emit bound SQL parameters, which may contain user-supplied content.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structured logger."""
    return structlog.stdlib.get_logger(name)
