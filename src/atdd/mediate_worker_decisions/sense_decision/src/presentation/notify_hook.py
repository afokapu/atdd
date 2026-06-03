"""cmux notification hook entrypoint.

Configured via ``.cmux/cmux.json`` to run on every notification. Receives the
notification policy JSON on stdin, senses a decision (if the surface maps to a
worker and shows a real prompt), and echoes the original payload back so the
desktop notification is never suppressed.
"""
from __future__ import annotations

import json
import sys
from typing import Optional, TextIO

from atdd.mediate_worker_decisions.sense_decision.src.application.sense_use_case import (
    SOURCE_NOTIFICATION,
    SenseDecisionUseCase,
)


def _notification_hash(payload: dict) -> str:
    import hashlib

    raw = json.dumps(payload.get("notification", {}), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def run(use_case: SenseDecisionUseCase, stdin: TextIO, stdout: TextIO) -> int:
    """Drive one notification through the sense use case; pass the payload through."""
    payload = json.load(stdin)
    notification = payload.get("notification", {}) or {}
    surface_id: Optional[str] = notification.get("surfaceId") or notification.get(
        "surface_id"
    )
    if surface_id:
        use_case.sense(
            surface_id=surface_id,
            source=SOURCE_NOTIFICATION,
            notification_hash=_notification_hash(payload),
        )
    json.dump(payload, stdout)
    return 0


def main(argv: Optional[list] = None) -> int:  # pragma: no cover - thin entrypoint
    from atdd.mediate_worker_decisions.sense_decision.composition import (
        build_sense_use_case_from_repo,
    )

    use_case = build_sense_use_case_from_repo()
    return run(use_case, sys.stdin, sys.stdout)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
