"""Deliberately-bad production sample: emits diagnostics via builtin print().

Pointing the enforcement test at this tree (ATDD_SCAN_TARGET=fixtures/dirty)
makes the detector find a violation, pytest fails, and the run adapter maps
exit 1 -> one violation keyed by coder.logging.print. Proves RED.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_user(uid: str) -> str:
    print(f"creating user {uid}")  # violation: console-print diagnostic in production code
    logger.info("user created", extra={"user_id": uid})
    return uid


def debug_dump(payload: dict) -> None:
    print("payload:", payload)  # violation: another bare print()
