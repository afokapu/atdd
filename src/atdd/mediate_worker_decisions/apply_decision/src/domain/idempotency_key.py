"""Pure idempotency key derivation (no I/O).

A stable key over (request_id, verdict_id) so a replayed verdict is delivered to
the worker at most once (WMBT E002).
"""
from __future__ import annotations

import hashlib


def idempotency_key(request_id: str, verdict_id: str) -> str:
    raw = f"{request_id}\x00{verdict_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
