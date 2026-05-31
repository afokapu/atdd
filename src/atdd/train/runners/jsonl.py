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

import hashlib
import logging
import threading
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
    def bind_policy(self, policy: PolicyHandle) -> None:
        """Bind the :class:`PolicyHandle` ``run_wave`` drives each issue with.

        ``start_issue`` sets ``self._policy`` itself; ``run_wave`` (Child 9) takes
        no ``policy`` argument (it is not in the §4.7 Protocol signature), so the
        CLI binds it here before the wave drive.
        """
        self._policy = policy

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
        """Replay a crashed run and continue from the next event (§6.3, Child 9).

        Deterministic crash-recovery: given identical
        ``(events.jsonl, conventions.snapshot.yaml, current external state)`` this
        reconstructs the same in-memory state and computes the same next decision
        as the loop that crashed, with no double-execution. Steps (§6.3):

        1. Load the run's FROZEN ``conventions.snapshot.yaml`` — never the current
           source conventions (which may have drifted since the run started).
        2. Replay ``events.jsonl`` to reconstruct the in-memory ``RunState``.
        3. Re-materialize evidence from current GitHub/filesystem state.
        4. Call ``coach.core.next_transition`` with the FROZEN conventions.
        5. Continue from the next event the loop would have written: append a
           ``RunResumed`` marker, then the recomputed ``DecisionMade`` event +
           ``decisions.jsonl`` row.

        Resume records the reconciled decision; it neither advances the phase
        label nor re-dispatches an agent, so calling it after a crash (or twice)
        never double-executes a phase that already ran.
        """
        from atdd.coach import core as coach_core
        from atdd.train.persistence import load_conventions_for_run

        run_id = RunId(str(run_id))

        # 1. FROZEN conventions snapshot (NOT live source) — replay determinism.
        run_dir = self._run_dir_for(run_id)
        conventions = load_conventions_for_run(run_dir)

        # 2. Reconstruct RunState by replaying the event log (raises if unknown).
        state = self.persistence.load_run(run_id)

        # Determinism guard (§6.3): the run's recorded conventions hash must match
        # the snapshot we just froze, or replay would not be deterministic.
        if state.conventions_hash and state.conventions_hash != conventions.snapshot_hash:
            raise RuntimeError(
                "conventions snapshot drift: replay would not be deterministic "
                f"(run recorded {state.conventions_hash!r}, snapshot is "
                f"{conventions.snapshot_hash!r}); see docs/coach-decomposition.md §6.3"
            )

        # 3. Re-materialize evidence from current external state.
        evidence = self.persistence.materialize_evidence(state.issue_number)

        # 4. Pure decision under the FROZEN conventions.
        decision = coach_core.next_transition(evidence, conventions)
        evidence_hash = self._evidence_hash(evidence)

        # 5. Continue from the next event the loop would have written.
        self.persistence.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts="",
                run_id=run_id,
                issue_number=state.issue_number,
                type="RunResumed",
                payload={
                    "from_event_seq": state.last_event_seq,
                    "resume_reason": "operator-resume",
                    "current_phase": state.current_phase.value,
                },
                seq=0,  # assigned by the store
            ),
        )
        self.persistence.append_decision(run_id, decision, evidence_hash=evidence_hash)
        self.persistence.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts="",
                run_id=run_id,
                issue_number=state.issue_number,
                type="DecisionMade",
                payload=_decision_made_payload(decision),
                seq=0,  # assigned by the store
            ),
        )

    def run_wave(
        self, issue_numbers: list[int], *, concurrency: int = 1
    ) -> WaveResult:
        """Drive a dependency-ordered wave of issues concurrently (§7.1, Child 9).

        Resolves the wave plan (``atdd.train.wave_runner.resolve_waves``), then
        drives each wave's members through ``start_issue`` concurrently, bounded
        by ``concurrency`` (the per-host ``train.concurrency.max_parallel_issues``
        cap, §7.4). Between-wave dependency ordering is preserved by the join
        barrier inside ``drive_wave_concurrently``: wave N+1 never starts until
        every member of wave N is terminal.

        Returns a :class:`WaveResult` partitioning the issues into the runs that
        started, the runs that ended BLOCKED, and the issues that failed to start
        (``(issue_number, reason)``). A driver that raises is captured as a
        ``failed_to_start`` entry, never propagated, so one member's failure can
        never abort its siblings (issue #730).
        """
        from atdd.train import wave_runner

        if self._policy is None:
            raise RuntimeError(
                "run_wave requires a bound PolicyHandle; call start_issue or "
                "bind_policy() first"
            )

        machines = {
            n: (self._state_machines.get(n) or self._fresh_state_machine(n))
            for n in issue_numbers
        }
        self._state_machines.update(machines)
        cfg = self._cfg if self._cfg is not None else self._fresh_cfg(issue_numbers)
        waves = wave_runner.resolve_waves(cfg)

        run_id_by_issue: dict[int, RunId] = {}
        failed: list[tuple[int, str]] = []
        lock = threading.Lock()

        def _drive(issue_num: int) -> int:
            try:
                run_id = self.start_issue(issue_num, policy=self._policy)
            except Exception as exc:  # noqa: BLE001 — capture, never abort siblings
                _log.warning(
                    "run_wave: issue failed to start",
                    extra={
                        "issue": issue_num,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                with lock:
                    failed.append((issue_num, f"{type(exc).__name__}: {exc}"))
                return 2
            with lock:
                run_id_by_issue[issue_num] = run_id
            return self.rc_for(run_id)

        for wave in waves:
            wave_runner.drive_wave_concurrently(wave, _drive, max_parallel=concurrency)

        started: list[RunId] = []
        blocked: list[RunId] = []
        for issue_num, run_id in run_id_by_issue.items():
            sm = self._state_machines.get(issue_num)
            phase = getattr(sm, "phase", None)
            if phase is not None and getattr(phase, "value", None) == "BLOCKED":
                blocked.append(run_id)
            else:
                started.append(run_id)

        return WaveResult(
            started=tuple(started),
            blocked=tuple(blocked),
            failed_to_start=tuple(failed),
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

    def _run_dir_for(self, run_id: RunId) -> Path:
        """Filesystem location of a run's durable dir (§5.1).

        Runs live under ``<repo_root>/.atdd/runtime/runs/<run_id>/`` — the same
        layout :class:`JsonlPersistenceStore` writes to — so resume can read the
        frozen ``conventions.snapshot.yaml`` for an arbitrary run id.
        """
        repo_root = getattr(self.persistence, "repo_root", None) or Path.cwd()
        return Path(repo_root) / ".atdd" / "runtime" / "runs" / str(run_id)

    @staticmethod
    def _evidence_hash(evidence: object) -> str:
        """Deterministic content hash of the materialized evidence (§5.2).

        Frozen ``Evidence`` dataclasses have a stable ``repr``, so hashing it
        yields the same digest for identical evidence — which is exactly the
        replay-determinism property resume relies on.
        """
        return hashlib.sha256(repr(evidence).encode("utf-8")).hexdigest()

    @staticmethod
    def _fresh_state_machine(issue_number: int):
        from atdd.coach.handlers.state_machine import initialize_state_machine

        return initialize_state_machine(issue_number)

    @staticmethod
    def _fresh_cfg(issue_numbers):
        from atdd.coach.commands.coach import Config

        nums = [issue_numbers] if isinstance(issue_numbers, int) else list(issue_numbers)
        return Config(issue_numbers=nums)


def _decision_made_payload(decision: object) -> dict:
    """Build the ``DecisionMade`` event payload from a ``TransitionDecision``.

    Mirrors the §5.2 ``DecisionMade`` required keys (``verdict_kind``,
    ``from_phase``, ``to_phase``, ``persona``, ``rule_ids``) so the resume
    continuation event validates against the events.jsonl schema.
    """
    verdict = getattr(decision, "verdict", None)
    to_phase = getattr(decision, "to_phase", None)
    persona = getattr(decision, "persona", None)
    return {
        "verdict_kind": getattr(getattr(verdict, "kind", None), "value", None),
        "from_phase": getattr(getattr(decision, "from_phase", None), "value", None),
        "to_phase": getattr(to_phase, "value", None) if to_phase is not None else None,
        "persona": getattr(persona, "value", None) if persona is not None else None,
        "rule_ids": list(getattr(verdict, "rule_ids", ()) or ()),
    }


__all__ = ["JsonlTrainRunner"]
