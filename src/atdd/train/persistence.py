"""Persistence contract for the train runner (docs/coach-decomposition.md §4.6).

Child 3 (#890) ships the *contract surface only*:

- the :class:`PersistenceStore` ``Protocol`` (every method from §4.6),
- :class:`IssueRecord` (manifest row shape, §4.7),
- the :func:`load_conventions` signature (§4.4) — first impl in Child 7.

Concrete implementations ship later:

- ``InMemoryPersistenceStore`` — Child 2 (#889), parity-test fixture.
- ``JsonlPersistenceStore`` + ``materialize_evidence`` body — Child 7 (#894).

This module is a typed seam; it performs no I/O at import time.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

from atdd.coach.core.types import (
    Conventions,
    Evidence,
    IssueType,
    Phase,
    TransitionDecision,
)
from atdd.train.types import (
    RunId,
    RunState,
    RunStatus,
    RunSummary,
    TrainEvent,
)


@dataclass(frozen=True)
class IssueRecord:
    """Manifest row shape — read/written by persistence (§4.7)."""

    id: str
    slug: str
    issue_number: int
    type: IssueType
    status: Phase
    train: str | None
    created: str
    archived: str | None


@runtime_checkable
class PersistenceStore(Protocol):
    """The bridge between the train runner and durable run state (§4.6).

    Method signatures are frozen here; the JSONL-backed implementation ships in
    Child 7. The single-writer invariant (only the train-runner layer calls
    :meth:`append_event`) is what makes replay deterministic (§5.2).
    """

    # --- run lifecycle ---
    def create_run(self, issue_number: int, *, conventions: Conventions) -> RunId: ...

    def load_run(self, run_id: RunId) -> RunState: ...

    def list_runs(self, *, status: RunStatus | None = None) -> list[RunSummary]: ...

    # --- events (single-writer: train runner) ---
    def append_event(self, run_id: RunId, event: TrainEvent) -> None: ...

    def replay_events(self, run_id: RunId) -> Iterator[TrainEvent]: ...

    # --- decisions (audit trail for every Coach Verdict) ---
    def append_decision(
        self, run_id: RunId, decision: TransitionDecision, *, evidence_hash: str
    ) -> None: ...

    # --- manifest (issue registry) ---
    def get_issue(self, n: int) -> IssueRecord: ...

    def upsert_issue(self, rec: IssueRecord) -> None: ...

    # --- evidence materialization (THE bridge to Coach-core) ---
    def materialize_evidence(self, issue_number: int) -> Evidence:
        """Aggregate from manifest, GitHub adapter, validators, filesystem into a
        frozen :class:`~atdd.coach.core.types.Evidence` snapshot. The conventions
        hash MUST match the active :class:`~atdd.coach.core.types.Conventions`.

        Body implemented in Child 7 (#894).
        """
        ...


def load_conventions(repo_root: Path) -> Conventions:
    """Load + normalize the convention YAML files, compute the snapshot hash, and
    freeze them into a :class:`~atdd.coach.core.types.Conventions` bundle (§4.4).

    Conventions are loaded once per run and frozen for the run's duration; the
    snapshot hash is recorded in the run's first event so replay is deterministic.
    Hot-reload mid-run is explicitly unsupported.

    Concrete implementation ships in Child 7 (#894).
    """
    raise NotImplementedError(
        "load_conventions ships in Child 7 (#894); "
        "see docs/coach-decomposition.md §4.4"
    )


__all__ = [
    "PersistenceStore",
    "IssueRecord",
    "load_conventions",
]
