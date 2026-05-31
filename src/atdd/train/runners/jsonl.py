"""JsonlTrainRunner — the default/first TrainRunner (docs/coach-decomposition.md §7.1, Child 8).

Wraps today's durable per-issue drive (now in :mod:`atdd.train.issue_runner`) with
the typed :class:`~atdd.train.runner_iface.TrainRunner` seam:

- ``start_issue`` creates a durable run via the Child 7 :class:`JsonlPersistenceStore`
  (writing the ``RunStarted`` event + conventions snapshot under
  ``.atdd/runtime/runs/<run_id>/``) and then drives the issue through
  ``issue_runner.drive_single_issue``.
- ``status`` reconstructs the run from its event log; the run's lifecycle state is
  derived from the recorded terminal events.
- ``cancel`` appends a ``RunCancelled`` event (a Child-8 events.jsonl schema
  addition — no Coach-core change, §5.2).
- ``resume`` + ``run_wave`` are the Child-9 (#896) surface and raise
  ``NotImplementedError`` here.

Layer discipline (§3.3): MAY import ``atdd.coach.*`` / ``atdd.train.*`` / stdlib;
MUST NOT import ``atdd.cli`` or ``atdd.observer``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import JsonlPersistenceStore, PersistenceStore
from atdd.train.runner_iface import PolicyHandle
from atdd.train.types import RunId, RunStatus, TrainEvent, WaveResult

_log = logging.getLogger("atdd.train.runner")

# events.jsonl → RunStatus lifecycle state (§4.7). The last terminal event wins.
_TERMINAL_EVENT_STATE: dict[str, str] = {
    "RunCancelled": "CANCELLED",
    "RunCompleted": "COMPLETED",
    "RunEscalated": "ESCALATED",
    "RunBlocked": "BLOCKED",
}


class JsonlTrainRunner:
    """Local JSONL-backed :class:`TrainRunner` (the migration's only runner)."""

    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        github: Optional[object] = None,
        agent: Optional[object] = None,
        cfg: Optional[object] = None,
        runtime_dir: Optional[Path] = None,
        drive_seams: Optional[dict] = None,
    ) -> None:
        self.persistence = persistence
        self.github = github
        self.agent = agent
        self._cfg = cfg
        self._runtime_dir = Path(runtime_dir) if runtime_dir is not None else None
        self._drive_seams = dict(drive_seams or {})
        self._policy: Optional[PolicyHandle] = None
        # Per-run results + the state-machine registry the CLI binds in.
        self._rc: dict[str, int] = {}
        self._state_machines: dict[int, object] = {}
        self._injected_by_issue: dict[int, object] = {}

    # --- CLI wiring -------------------------------------------------------- #
    def bind_state_machines(self, machines: dict[int, object]) -> None:
        """Register the per-issue StateMachine objects the cold-start drives.

        Keeps ``start_issue`` driving the *same* StateMachine the wave bookkeeping
        inspects (e.g. for BLOCKED detection), so the runner is a drop-in for the
        previous direct ``_drive_single_issue`` call.
        """
        self._state_machines = dict(machines)

    def bind_drive_context(
        self,
        *,
        cfg: Optional[object] = None,
        runtime_dir: Optional[Path] = None,
        spawn_func: Optional[Callable] = None,
        two_phase_func: Optional[Callable] = None,
        max_loop_events: Optional[int] = None,
        run_id_sink: Optional[list] = None,
        injected_events: Optional[dict] = None,
    ) -> None:
        """Thread the cold-start drive seams (test seams + per-issue injected
        events) into the runner so ``start_issue`` reproduces the previous
        ``_drive_single_issue`` call exactly (production passes all ``None``)."""
        if cfg is not None:
            self._cfg = cfg
        if runtime_dir is not None:
            self._runtime_dir = Path(runtime_dir)
        self._drive_seams = {
            "_spawn_func": spawn_func,
            "_two_phase_func": two_phase_func,
            "_max_loop_events": max_loop_events,
            "_run_id_sink": run_id_sink,
        }
        self._injected_by_issue = dict(injected_events or {})

    def rc_for(self, run_id: RunId) -> int:
        """Process return-code recorded by the most recent ``start_issue`` drive."""
        return self._rc.get(str(run_id), 0)

    # --- TrainRunner protocol --------------------------------------------- #
    def start_issue(self, issue_number: int, *, policy: PolicyHandle) -> RunId:
        self._policy = policy
        run_id = self.persistence.create_run(issue_number, conventions=policy.conventions)

        from atdd.train import issue_runner

        sm = self._state_machines.get(issue_number) or self._fresh_state_machine(issue_number)
        cfg = self._cfg if self._cfg is not None else self._fresh_cfg(issue_number)
        runtime_dir = self._runtime_dir or self._default_runtime_dir()

        seams = {
            "_spawn_func": self._drive_seams.get("_spawn_func"),
            "_two_phase_func": self._drive_seams.get("_two_phase_func"),
            "_max_loop_events": self._drive_seams.get("_max_loop_events"),
            "_run_id_sink": self._drive_seams.get("_run_id_sink"),
            "_injected_events": self._injected_by_issue.get(issue_number),
        }
        rc = issue_runner.drive_single_issue(cfg, sm, runtime_dir, **seams)
        self._rc[str(run_id)] = rc
        return run_id

    def handle_event(self, run_id: RunId, event: object) -> None:
        """Append a train event to the run's single-writer log (§5.2).

        Accepts a :class:`TrainEvent` or a ``{"type": ..., "payload": ...}`` dict.
        """
        self.persistence.append_event(run_id, self._coerce_event(run_id, event))

    def status(self, run_id: RunId) -> RunStatus:
        state = self.persistence.load_run(run_id)
        events = list(self.persistence.replay_events(run_id))
        lifecycle = "RUNNING"
        for e in events:  # last terminal event wins
            if e.type in _TERMINAL_EVENT_STATE:
                lifecycle = _TERMINAL_EVENT_STATE[e.type]
        started_at = events[0].ts if events else ""
        last_event_at = events[-1].ts if events else ""
        return RunStatus(
            run_id=run_id,
            issue_number=state.issue_number,
            current_phase=state.current_phase,
            state=lifecycle,
            last_event_seq=state.last_event_seq,
            started_at=started_at,
            last_event_at=last_event_at,
        )

    def cancel(self, run_id: RunId, *, reason: str) -> None:
        state = self.persistence.load_run(run_id)
        self.persistence.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts="",
                run_id=run_id,
                issue_number=state.issue_number,
                type="RunCancelled",
                payload={"reason": reason},
                seq=0,  # assigned by the store
            ),
        )

    def resume(self, run_id: RunId) -> None:
        raise NotImplementedError(
            "JsonlTrainRunner.resume ships in Child 9 (#896); see "
            "docs/coach-decomposition.md §6.3"
        )

    def run_wave(
        self, issue_numbers: list[int], *, concurrency: int = 1
    ) -> WaveResult:
        raise NotImplementedError(
            "JsonlTrainRunner.run_wave ships in Child 9 (#896); see "
            "docs/coach-decomposition.md §7.1"
        )

    # --- internals --------------------------------------------------------- #
    def _coerce_event(self, run_id: RunId, event: object) -> TrainEvent:
        if isinstance(event, TrainEvent):
            return event
        if isinstance(event, dict):
            state = self.persistence.load_run(run_id)
            return TrainEvent(
                schema_version=event.get("schema_version", SCHEMA_VERSION),
                ts=event.get("ts", ""),
                run_id=run_id,
                issue_number=event.get("issue_number", state.issue_number),
                type=event.get("type", "AgentEventReceived"),
                payload=event.get("payload", {}),
                seq=0,  # assigned by the store
            )
        raise TypeError(f"handle_event expects a TrainEvent or dict, got {type(event)!r}")

    def _default_runtime_dir(self) -> Path:
        repo_root = getattr(self.persistence, "repo_root", None) or Path.cwd()
        return Path(repo_root) / ".atdd" / "runtime"

    @staticmethod
    def _fresh_state_machine(issue_number: int):
        from atdd.coach.handlers.state_machine import initialize_state_machine

        return initialize_state_machine(issue_number)

    @staticmethod
    def _fresh_cfg(issue_number: int):
        from atdd.coach.commands.coach import Config

        return Config(issue_numbers=[issue_number])


__all__ = ["JsonlTrainRunner"]
