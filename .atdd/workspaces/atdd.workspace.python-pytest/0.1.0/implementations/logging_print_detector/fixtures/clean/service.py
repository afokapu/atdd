"""Clean production sample: routes diagnostics through a structured logger.

Used by test_logging_print.py as the default scan target — scanning this tree
yields zero coder.logging.print violations, so the implementation runs GREEN by
default (provider maps exit 0 -> no violation).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_user(uid: str) -> str:
    logger.info("user created", extra={"user_id": uid})
    return uid


def fetch(host: str, retries: int) -> None:
    try:
        _connect(host)
    except ConnectionError as exc:
        logger.error("connect failed", extra={"host": host, "retries": retries, "error": str(exc)})
        raise


def _connect(host: str) -> None:
    # A method named print on an object must NOT trip the detector — only the
    # builtin bare-name print() does. This guards against false positives.
    formatter = logging.Formatter()
    formatter.format  # attribute access, not a print call
    del host
