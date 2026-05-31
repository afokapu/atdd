"""Train-runner supporting types (docs/coach-decomposition.md §4.7).

These are the run/event value types the ``PersistenceStore`` Protocol (§4.6) and
the ``TrainRunner`` Protocol (§4.7, Child 8) bind to. They are plain frozen
dataclasses / ``NewType`` aliases — no behaviour, no I/O — so both the
persistence layer (Child 3/7) and the runner layer (Child 8) can import them
without a dependency cycle.

Physical-location note (§4.7): ``RunId``, ``RunStatus``, ``RunSummary``,
``RunState``, ``WaveResult`` and ``TrainEvent`` live here in ``atdd.train.types``.
``IssueRecord`` lives in ``atdd.train.persistence``. ``MergeResult`` lives in
``atdd.integrations.github.types`` (Child 4).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NewType

from atdd.coach.core.types import Phase, TransitionDecision

# Opaque run identifier, e.g. "run-816-2026-05-30-a81b0d90" (§4.7).
RunId = NewType("RunId", str)

# Lifecycle state of a run, shared by RunStatus / RunSummary (§4.7).
RunLifecycle = Literal["RUNNING", "BLOCKED", "ESCALATED", "COMPLETED", "CANCELLED"]


@dataclass(frozen=True)
class RunStatus:
    run_id: RunId
    issue_number: int
    current_phase: Phase
    state: RunLifecycle
    last_event_seq: int
    started_at: str
    last_event_at: str


@dataclass(frozen=True)
class RunSummary:
    run_id: RunId
    issue_number: int
    state: RunLifecycle


@dataclass(frozen=True)
class RunState:
    """Materialized in-memory state reconstructed from event replay (§4.7)."""

    run_id: RunId
    issue_number: int
    current_phase: Phase
    conventions_hash: str
    decisions: tuple[TransitionDecision, ...]
    last_event_seq: int


@dataclass(frozen=True)
class WaveResult:
    started: tuple[RunId, ...]
    blocked: tuple[RunId, ...]
    failed_to_start: tuple[tuple[int, str], ...]  # (issue_number, reason)


@dataclass(frozen=True)
class TrainEvent:
    """Unified shape for events appended to events.jsonl (§5.2)."""

    schema_version: str
    ts: str
    run_id: RunId
    issue_number: int
    type: str
    payload: dict
    seq: int  # monotonic per run


__all__ = [
    "RunId",
    "RunLifecycle",
    "RunStatus",
    "RunSummary",
    "RunState",
    "WaveResult",
    "TrainEvent",
]
