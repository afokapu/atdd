"""Single coach event queue with per-event-type natural-key dedup.

Mirrors the idempotency table in ``event-semantics.md`` (#483). All three
J5 watchers (runtime/git/liveness) feed this queue; the natural-key
dedup is what makes at-least-once producers surface as exactly-once to
the consumer per the spec §4.4 contract.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Optional


# How a queue/replay layer dedupes an event into a single
# consumer-visible emission. Each entry is the tuple of payload-path
# components (plus optional top-level keys like ``agent_id``) that form
# the natural key. Source: ``event-semantics.md`` (#483).
NATURAL_KEY: dict[str, tuple[str, ...]] = {
    "agent_spawned":       ("agent_id",),
    "heartbeat":           ("agent_id", "payload.observed_at"),
    "commit_observed":     ("payload.sha",),
    "event_emitted":       ("payload.original_event_id", "payload.original_event_type"),
    "escalation_emitted":  ("payload.judgment_id",),
    "pr_opened":           ("payload.pr_number",),
    "pr_closed":           ("payload.pr_number", "payload.terminal_state"),
    "validation_pending":  ("payload.coach_run_id", "payload.phase", "payload.sha"),
    "validation_complete": ("payload.coach_run_id", "payload.phase", "payload.sha"),
    "review_complete":     ("payload.issue_number", "payload.aggregate_sha"),
    "correction_emitted":  ("agent_id", "payload.rule_id", "payload.detected_at"),
    "process_silence":     ("agent_id", "payload.silence_window_started_at"),
}

# Replay behavior on coach --resume / watcher restart, per
# ``event-semantics.md``.
#   "cached"     — republish the prior event from durable state
#   "suppressed" — never re-emit on resume
REPLAY_BEHAVIOR: dict[str, str] = {
    "agent_spawned":       "cached",
    "heartbeat":           "suppressed",
    "commit_observed":     "cached",
    "event_emitted":       "cached",
    "escalation_emitted":  "suppressed",
    "pr_opened":           "cached",
    "pr_closed":           "cached",
    "validation_pending":  "suppressed",
    "validation_complete": "cached",
    "review_complete":     "cached",
    "correction_emitted":  "suppressed",
    "process_silence":     "suppressed",
}


def natural_key(event: dict) -> tuple:
    """Return the dedup key for ``event`` per ``NATURAL_KEY``.

    For unknown event types the key is the full event-type +
    timestamp + ``id(event)`` triple so unrelated events never collide.
    """
    et = event.get("event_type")
    paths = NATURAL_KEY.get(et)
    if paths is None:
        return (et, event.get("timestamp"), id(event))
    parts: list[Any] = [et]
    for path in paths:
        if "." in path:
            top, rest = path.split(".", 1)
            parts.append((event.get(top) or {}).get(rest))
        else:
            parts.append(event.get(path))
    return tuple(parts)


class CoachEventQueue:
    """Single coach event queue shared by all three J5 watchers.

    ``put()`` deduplicates by ``natural_key()`` so duplicate emissions
    (replay overlap, multi-watcher races, restart re-fires) collapse to
    one consumer-visible event.
    """

    def __init__(self, runtime_dir) -> None:  # accepts Path or str
        from pathlib import Path
        self.runtime_dir = Path(runtime_dir)
        self._items: deque[dict] = deque()
        self._seen: set[tuple] = set()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    def put(self, event: dict) -> bool:
        key = natural_key(event)
        with self._cv:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._items.append(event)
            self._cv.notify()
            return True

    def get(self, timeout: Optional[float] = None) -> Optional[dict]:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cv:
            while not self._items:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._cv.wait(timeout=remaining)
            return self._items.popleft()

    def drain(self) -> list[dict]:
        with self._cv:
            out = list(self._items)
            self._items.clear()
            return out

    def __len__(self) -> int:
        with self._cv:
            return len(self._items)
