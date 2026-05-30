"""``InMemoryPersistenceStore`` — the parity test's persistence double (Child 2).

Models the slice of the §4.6 ``PersistenceStore`` protocol the dry-run runner
needs: run creation, append-only event log, a decision audit trail, and the
current phase per run. Events are kept in memory as ``StoredEvent`` records; the
single-writer rule (§5.2) is honoured because only ``LocalDryRunRunner`` appends.

``from_events`` reconstructs a fresh store from a replayed event stream — this is
what powers the parity test's replay-determinism assertion (§6.3): rebuild from
the log, re-run the pure coach-core decisions, and the decision list must match.

The durable ``JsonlPersistenceStore`` that fulfils the full protocol ships in
Child 7; this in-memory store is the test fixture the spec assigns to Child 2
(§4.6 implementations table).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from atdd.coach.core.types import Phase, TransitionDecision


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    type: str
    payload: dict


@dataclass
class _Run:
    run_id: str
    issue_number: int
    current_phase: Phase
    conventions_hash: str
    events: list[StoredEvent] = field(default_factory=list)
    decisions: list[TransitionDecision] = field(default_factory=list)
    seq: int = 0


class InMemoryPersistenceStore:
    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}
        self._counter = 0

    # --- run lifecycle --------------------------------------------------- #
    def create_run(
        self, issue_number: int, *, current_phase: Phase, conventions_hash: str
    ) -> str:
        self._counter += 1
        run_id = f"run-{issue_number}-{self._counter:04d}"
        self._runs[run_id] = _Run(
            run_id=run_id,
            issue_number=issue_number,
            current_phase=current_phase,
            conventions_hash=conventions_hash,
        )
        return run_id

    def issue_number(self, run_id: str) -> int:
        return self._runs[run_id].issue_number

    def conventions_hash(self, run_id: str) -> str:
        return self._runs[run_id].conventions_hash

    def current_phase(self, run_id: str) -> Phase:
        return self._runs[run_id].current_phase

    def set_current_phase(self, run_id: str, phase: Phase) -> None:
        self._runs[run_id].current_phase = phase

    # --- events (single-writer: the train runner) ----------------------- #
    def append_event(self, run_id: str, event_type: str, payload: dict) -> None:
        run = self._runs[run_id]
        run.seq += 1
        run.events.append(StoredEvent(seq=run.seq, type=event_type, payload=dict(payload)))

    def replay_events(self, run_id: str) -> list[StoredEvent]:
        return list(self._runs[run_id].events)

    # --- decisions (audit trail for every coach Verdict) ---------------- #
    def append_decision(self, run_id: str, decision: TransitionDecision) -> None:
        self._runs[run_id].decisions.append(decision)

    def decisions(self, run_id: str) -> list[TransitionDecision]:
        return list(self._runs[run_id].decisions)

    # --- replay reconstruction ------------------------------------------ #
    @classmethod
    def from_events(cls, events: Iterable[StoredEvent]) -> "InMemoryPersistenceStore":
        """Rebuild a store seeded from a replayed event stream.

        The ``RunStarted`` event carries everything needed to re-seat the run
        (run_id, issue_number, initial phase, conventions hash). Decisions are
        intentionally NOT restored — replay recomputes them from the log so the
        parity test can prove determinism.
        """
        events = list(events)
        started = next(e for e in events if e.type == "RunStarted")
        run_id = started.payload["run_id"]

        store = cls()
        store._runs[run_id] = _Run(
            run_id=run_id,
            issue_number=started.payload["issue_number"],
            current_phase=Phase(started.payload["initial_phase"]),
            conventions_hash=started.payload["conventions_hash"],
            events=list(events),
            seq=max((e.seq for e in events), default=0),
        )
        return store

    def materialized_phases(self, run_id: str) -> Iterator[Phase]:
        """Phases at which evidence was materialized, in order (drives replay)."""
        for event in self._runs[run_id].events:
            if event.type == "EvidenceMaterialized":
                yield Phase(event.payload["current_phase"])
