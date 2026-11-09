"""Minimal standard-library logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Configure consistent console logging without message or secret payloads."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
