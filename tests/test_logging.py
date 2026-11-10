"""Logging redaction and rendering tests."""

import json
import logging

import pytest

from whisprlink.logging_config import REDACTED, configure_logging, get_logger, redact_sensitive

BOT_TOKEN = "123456789:AAH-valid_looking_token_value_1234567"


def test_sensitive_keys_are_masked() -> None:
    event = redact_sensitive(
        None,
        "info",
        {
            "event": "x",
            "telegram_bot_token": "abc",
            "deep_link_secret": "abc",
            "DATABASE_URL": "postgresql://u:p@h/db",
            "text": "hello private message",
            "caption": "private caption",
            "context": "kept",
            "user_id": 5,
        },
    )

    assert event["telegram_bot_token"] == REDACTED
    assert event["deep_link_secret"] == REDACTED
    assert event["DATABASE_URL"] == REDACTED
    assert event["text"] == REDACTED
    assert event["caption"] == REDACTED
    assert event["context"] == "kept"
    assert event["user_id"] == 5


def test_bot_tokens_and_url_passwords_are_scrubbed_from_values() -> None:
    event = redact_sensitive(
        None,
        "info",
        {
            "event": f"calling https://api.telegram.org/bot{BOT_TOKEN}/getMe",
            "target": "postgresql+asyncpg://whisprlink:hunter2@db:5432/whisprlink",
        },
    )

    assert BOT_TOKEN not in event["event"]
    assert "hunter2" not in event["target"]
    assert "whisprlink:" in event["target"]


def test_json_output_is_structured_and_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")

    get_logger("whisprlink.test").info("something_happened", password="p", attempt=3)

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["event"] == "something_happened"
    assert record["level"] == "info"
    assert record["attempt"] == 3
    assert record["password"] == REDACTED
    assert record["timestamp"].endswith("Z")


def test_standard_library_loggers_use_the_same_pipeline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO", "json")

    logging.getLogger("aiogram.dispatcher").warning("token %s leaked", BOT_TOKEN)

    output = capsys.readouterr().out
    assert BOT_TOKEN not in output
    assert json.loads(output.strip().splitlines()[-1])["logger"] == "aiogram.dispatcher"


def test_console_format_and_level_filtering(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", "console")

    logger = get_logger("whisprlink.test")
    logger.info("hidden")
    logger.warning("visible")

    output = capsys.readouterr().out
    assert "visible" in output
    assert "hidden" not in output


def test_sql_statement_logging_stays_quiet() -> None:
    configure_logging("DEBUG", "json")

    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


def test_exception_tracebacks_and_nested_context_are_redacted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("ERROR", "json")
    database_password = "exception-db-password"
    nested_secret = "nested-authorization-secret"

    try:
        raise RuntimeError(
            "connection failed for "
            f"postgresql+asyncpg://whisprlink:{database_password}@db:5432/whisprlink "
            f"while calling Telegram token {BOT_TOKEN}"
        )
    except RuntimeError:
        get_logger("whisprlink.test").exception(
            "database_operation_failed",
            context={
                "nested": {
                    "authorization": nested_secret,
                    "message_text": "private message content",
                }
            },
        )

    output = capsys.readouterr().out
    for secret in (database_password, nested_secret, BOT_TOKEN, "private message content"):
        assert secret not in output

    record = json.loads(output.strip().splitlines()[-1])
    assert REDACTED in json.dumps(record)
