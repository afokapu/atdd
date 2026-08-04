"""Watcher handler — J5 wiring (issue #587).

Translates ``CoachEventQueue`` events into proposed phase transitions and
drives each per-issue ``StateMachine`` reactively.  Architecture per spec
review comment (issue #587):

- ``RuntimeWatcher`` runs in a background thread, feeds the shared queue.
- ``GitWatcher`` and ``LivenessChecker`` are called as synchronous tasks
  from the asyncio-style event-processing layer.
- All state-machine mutations happen on the single caller thread (the
  ``WatcherEventLoop`` methods), so no locks are needed for the machines.
- SIGTERM → ``shutdown()`` → stops background thread + persists checkpoint.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from atdd.coach.commands.durability import DecisionWriter
from atdd.coach.commands.event_queue import CoachEventQueue
from atdd.coach.commands.runtime_watcher import RuntimeWatcher
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    StateMachine,
    Transition,
    can_transition,
)


# ---------------------------------------------------------------------------
# Required module-level stub (per handler interface contract)
# ---------------------------------------------------------------------------


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    """Per-transition hook — NOOP; watcher drives via WatcherEventLoop."""
    return HandlerResult.NOOP


# ---------------------------------------------------------------------------
# Event-to-transition mapping
# ---------------------------------------------------------------------------

_PHASE_TRAILER_MAP: dict[str, Phase] = {
    "INIT": Phase.INIT,
    "PLANNED": Phase.PLANNED,
    "RED": Phase.RED,
    "GREEN": Phase.GREEN,
    "SMOKE": Phase.SMOKE,
    "REFACTOR": Phase.REFACTOR,
    "COMPLETE": Phase.COMPLETE,
}

_ADVANCE_FROM: dict[Phase, Phase] = {
    # A commit_observed with Phase: X trailer means the agent just completed
    # phase X → advance past it to the next phase.
    Phase.RED: Phase.GREEN,
    Phase.GREEN: Phase.SMOKE,
    Phase.SMOKE: Phase.REFACTOR,
    Phase.REFACTOR: Phase.COMPLETE,
}


def _proposed_transition(sm: StateMachine, event: dict) -> Optional[Transition]:
    """Map a raw queue event to a (src, dst) Transition for ``sm``, or None."""
    et = event.get("event_type")
    if et != "commit_observed":
        return None
    payload = event.get("payload") or {}
    trailers = payload.get("trailers") or {}
    issue_str = trailers.get("Issue")
    if issue_str is None or str(sm.issue_number) != str(issue_str):
        return None
    phase_str = trailers.get("Phase")
    if not phase_str:
        return None
    completed = _PHASE_TRAILER_MAP.get(phase_str)
    if completed is None or completed != sm.phase:
        return None
    dst = _ADVANCE_FROM.get(completed)
    if dst is None:
        return None
    if not can_transition(sm.phase, dst):
        return None
    return Transition(sm.phase, dst)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# WatcherEventLoop
# ---------------------------------------------------------------------------


class WatcherEventLoop:
    """Reactive driver that attaches J5 watchers to the per-issue state machines.

    Parameters
    ----------
    machines:
        List of ``StateMachine`` objects to manage.
    runtime_dir:
        Root of the ``.atdd/runtime/`` tree.
    queue:
        Shared ``CoachEventQueue`` that all watchers feed.
    stale_warn_minutes:
        If set, emit an escalation after this many minutes without events.
    escalation_channel:
        String name of the channel to escalate to (e.g. ``"slack:#coach"``).
    _escalation_sink:
        Optional list; if provided, escalation dicts are appended here
        instead of going to stderr (used in tests).
    worktree:
        Where the transition gate resolves an approval token from (#1619).
        Defaults to the cwd, matching every other gate caller.
    gate_config:
        The ``gate.transitions`` config this loop is held to (#1619). Defaults to
        the worktree's own ``.atdd/config.yaml``, so the watcher gates exactly as
        the CLI does in that repo.
    """

    def __init__(
        self,
        *,
        machines: list[StateMachine],
        runtime_dir: Path,
        queue: CoachEventQueue,
        stale_warn_minutes: Optional[int],
        escalation_channel: Optional[str],
        _escalation_sink: Optional[list] = None,
        coach_run_id: Optional[str] = None,
        worktree: Optional[Path] = None,
        gate_config: Optional[dict] = None,
    ) -> None:
        self.machines = machines
        self.runtime_dir = Path(runtime_dir)
        self.queue = queue
        self.stale_warn_minutes = stale_warn_minutes
        self.escalation_channel = escalation_channel
        self._escalation_sink = _escalation_sink
        self.coach_run_id = coach_run_id or str(uuid.uuid4())
        self.worktree = Path(worktree) if worktree is not None else Path.cwd()
        self._gate_config = gate_config
        self._stale_warned = False

        self.runtime_watcher = RuntimeWatcher(
            runtime_dir=self.runtime_dir,
            queue=self.queue,
        )
        self._decision_writer = self._make_decision_writer()
        self._shutdown_called = False

    def _make_decision_writer(self) -> Optional[DecisionWriter]:
        try:
            return DecisionWriter(runtime_dir=self.runtime_dir)
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
            return None

    # --- background watchers ------------------------------------------------

    def start_background_watchers(self) -> None:
        """Start the RuntimeWatcher background thread."""
        self.runtime_watcher.start()

    # --- event processing ---------------------------------------------------

    def process_one_event(self, *, timeout: float = 1.0) -> Optional[str]:
        """Consume one event from the queue and apply the resulting transition.

        Returns ``"applied"`` if a transition fired, ``"refused"`` if the gate
        declined one, ``"ignored"`` if no machine proposed one, or ``None`` if the
        queue was empty within ``timeout``.
        """
        event = self.queue.get(timeout=timeout)
        if event is None:
            return None
        return self._dispatch(event)

    def process_pending_events(self, *, max_events: int = 1000) -> int:
        """Drain up to ``max_events`` from the queue in timestamp order.

        Returns the number of transitions applied.
        """
        pending: list[dict] = []
        ev = self.queue.get(timeout=0.0)
        while ev is not None:
            pending.append(ev)
            ev = self.queue.get(timeout=0.0)

        pending.sort(key=lambda e: e.get("timestamp") or "")
        applied = 0
        for event in pending[:max_events]:
            if self._dispatch(event) == "applied":
                applied += 1
        return applied

    def _dispatch(self, event: dict) -> str:
        """Route one event. Returns what actually happened to it.

        ``"refused"`` is reported apart from ``"ignored"`` (#1619): an event that
        proposed a real transition the GATE declined is a different fact from an
        event no machine cared about, and collapsing them would leave a refused
        advance counted as applied — the same "absence reads as a normal outcome"
        defect this issue exists to remove.
        """
        for sm in self.machines:
            t = _proposed_transition(sm, event)
            if t is not None:
                return "applied" if self._apply_transition(sm, t, event) else "refused"
        return "ignored"

    def _apply_transition(
        self, sm: StateMachine, t: Transition, source_event: dict
    ) -> bool:
        """Evaluate the gate, then write the decision record and mutate the machine.

        Returns True if the machine advanced, False if the gate refused.

        Before #1619 this path evaluated NO gate at all — it was not a path where
        the gate fired and found nothing; there was no gate call. Every gated edge
        the watcher crossed was crossed unchallenged.

        DECISION 5 — RECORD AND REFUSE, not block silently. The synchronous paths
        have a caller who receives a non-zero exit and a printed reason. The
        watcher has none, so a silent no-op would make a GATED event
        indistinguishable from an IGNORED one — the same defect class as the
        fail-open this issue closes: an absence that reads as a normal outcome.
        On refusal it therefore writes a refusal record and leaves the machine
        exactly where it was.
        """
        if not self._gate_allows(sm, t, source_event):
            return False
        decision_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "decision_id": decision_id,
            "timestamp": _now_iso(),
            "coach_run_id": self.coach_run_id,
            "issue_number": sm.issue_number,
            "decision_type": "phase-transition",
            "inputs": {
                "event_type": source_event.get("event_type"),
                "sha": (source_event.get("payload") or {}).get("sha"),
                "from_phase": t.src.value,
            },
            "outcome": {
                "from_phase": t.src.value,
                "to_phase": t.dst.value,
            },
        }
        if self._decision_writer is not None:
            try:
                self._decision_writer.append(record)
            except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
                print(f"[watcher] decision write failed: {exc}", file=sys.stderr)

        sm.history.append(sm.phase)
        sm.phase = t.dst
        return True

    def _gate_allows(
        self, sm: StateMachine, t: Transition, source_event: dict
    ) -> bool:
        """Whether the enforcing transition gate permits this advance (#1619).

        On refusal, records it under ``phase-transition-refused`` and returns
        False. The type is deliberately NOT ``phase-transition``: that is the type
        ``resume.reconstruct_state`` rebuilds phases from, so a refusal wearing it
        could be replayed as a reached phase by a later resume run.
        """
        from atdd.coach.gate.decision import GateContext
        from atdd.coach.gate.enforcement import enforce_transition_gate

        outcome = enforce_transition_gate(
            self._resolve_gate_config(),
            GateContext(
                issue_number=sm.issue_number,
                from_phase=t.src.value,
                to_phase=t.dst.value,
                worktree=self.worktree,
            ),
        )
        if outcome.proceed:
            return True

        reasons = [f"[{b.gate_id} / {b.rule_id}] {b.message}" for b in outcome.blockers]
        print(
            f"[watcher] #{sm.issue_number}: transition gate REFUSED "
            f"{t.src.value}->{t.dst.value}; the state machine was not advanced "
            f"({len(outcome.blockers)} check(s) blocked).",
            file=sys.stderr,
        )
        for reason in reasons:
            print(f"[watcher]   ✗ {reason}", file=sys.stderr)

        if self._decision_writer is not None:
            try:
                self._decision_writer.append({
                    "decision_id": str(uuid.uuid4()),
                    "timestamp": _now_iso(),
                    "coach_run_id": self.coach_run_id,
                    "issue_number": sm.issue_number,
                    "decision_type": "phase-transition-refused",
                    "inputs": {
                        "event_type": source_event.get("event_type"),
                        "sha": (source_event.get("payload") or {}).get("sha"),
                        "from_phase": t.src.value,
                        "proposed_phase": t.dst.value,
                    },
                    "outcome": {"transitioned": False, "blockers": reasons},
                })
            except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
                print(f"[watcher] refusal write failed: {exc}", file=sys.stderr)
        return False

    def _resolve_gate_config(self) -> dict:
        """The ``gate.transitions`` config this loop is held to.

        An explicit ``gate_config`` wins; otherwise the worktree's own
        ``.atdd/config.yaml``. An unreadable or absent config yields ``{}``, which
        leaves ``DEFAULT_GATED_TRANSITIONS`` in charge — it gates MORE, never less.
        """
        if self._gate_config is not None:
            return self._gate_config
        import yaml

        path = self.worktree / ".atdd" / "config.yaml"
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            print(
                f"[watcher] .atdd/config.yaml at {path} is unreadable ({exc}); "
                f"falling back to the built-in gated-transition defaults",
                file=sys.stderr,
            )
            return {}

    # --- stale-warn ---------------------------------------------------------

    def check_stale(self, *, elapsed_minutes: float) -> None:
        """Emit a stale escalation if ``elapsed_minutes`` exceeds the threshold.

        Bounded: exactly one escalation per silence window (``_stale_warned``
        resets when an event arrives via ``reset_stale_timer()``).
        """
        if self.stale_warn_minutes is None:
            return
        if self._stale_warned:
            return
        if elapsed_minutes < self.stale_warn_minutes:
            return
        self._stale_warned = True
        self._emit_escalation(elapsed_minutes)

    def reset_stale_timer(self) -> None:
        """Reset the stale window after a live event is received."""
        self._stale_warned = False

    def _emit_escalation(self, elapsed_minutes: float) -> None:
        payload = {
            "level": "INFO",
            "channel": self.escalation_channel,
            "message": (
                f"[coach] no events for {elapsed_minutes:.1f} min "
                f"(stale-warn={self.stale_warn_minutes})"
            ),
            "timestamp": _now_iso(),
        }
        if self._escalation_sink is not None:
            self._escalation_sink.append(payload)
        else:
            print(
                f"[coach:stale-warn] {payload['message']}",
                file=sys.stderr,
            )

    # --- shutdown -----------------------------------------------------------

    def shutdown(self) -> None:
        """Clean shutdown: stop background thread + persist checkpoint.

        Idempotent — safe to call multiple times.
        """
        if self._shutdown_called:
            return
        self._shutdown_called = True
        self.runtime_watcher.stop()
        try:
            self.runtime_watcher.persist_checkpoint()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
            print(f"[watcher] checkpoint persist failed: {exc}", file=sys.stderr)
