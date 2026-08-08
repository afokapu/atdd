"""`atdd coach --resume <run-id>` runner — issue #511 / J6.

Closes the durability loop. Reads `.atdd/runtime/coach/decisions.jsonl`,
filters by `coach_run_id`, reconstructs the per-issue state-machine
position (the most recent reached phase per issue), then drives the
state machine forward to COMPLETE while consuming the idempotency
contract from #498 / P001 so already-logged transitions never
double-execute.

The resume runner is the consumer of three producers:

- ``decisions.jsonl`` (#498 / P001) — the durable transition log,
  source of truth for "what already happened".
- Idempotent worktree creation (#502 / E001) — re-running Phase A on
  resume is a no-op for already-recorded creations.
- Reattachable runtime watcher (#510 / M001) — events whose handlers
  already completed (visible via ``decisions.jsonl``) are NOT
  re-emitted; events that occurred during the kill window are
  delivered now.

Per spec §4.5: "On `--resume <run-id>`, coach reconstructs
state-machine positions from the log. Actions are idempotent."

Public surface:

- ``read_decisions(runtime_dir, run_id)`` — load and filter the log.
- ``reconstruct_state(runtime_dir, run_id)`` — most-recent phase per
  issue, scoped to the run.
- ``ResumeRunner`` — drives the lifecycle from a reconstructed state,
  reattaches watchers, refuses to re-run already-logged transitions.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from atdd.coach.commands.coach import (
    PLANNED_PATH,
    Phase,
    can_transition,
)
from atdd.coach.commands.durability import DecisionWriter
from atdd.coach.commands.event_queue import (
    CoachEventQueue,
    NATURAL_KEY,
    natural_key,
)
from atdd.coach.commands.runtime_watcher import RuntimeWatcher


logger = logging.getLogger(__name__)

TransitionAction = Callable[[int, str, str], dict]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _phase_transition_decision_id(run_id: str, issue: int, src: str, dst: str) -> str:
    return f"{run_id}:#{issue}:{src}->{dst}"


def read_decisions(runtime_dir: Path, run_id: str) -> list[dict]:
    """Return decision records for ``run_id``, in file (append) order."""
    path = Path(runtime_dir) / "coach" / "decisions.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("coach_run_id") == run_id:
                records.append(rec)
    return records


def reconstruct_state(runtime_dir: Path, run_id: str) -> dict[int, str]:
    """Return ``{issue_number: phase_name}`` for the resumed run.

    The phase is the most recent ``target_phase`` per issue across all
    ``phase-transition`` decisions for the run. Issues mentioned only
    in non-transition decisions (``worktree-create``, ``agent-spawn``)
    have no reconstructed phase entry — the state-machine position is
    defined exclusively by ``phase-transition`` records per spec §4.5.
    """
    state: dict[int, str] = {}
    for rec in read_decisions(runtime_dir, run_id):
        if rec.get("decision_type") != "phase-transition":
            continue
        issue = rec.get("issue_number")
        target = (rec.get("inputs") or {}).get("target_phase")
        if issue is None or target is None:
            continue
        state[issue] = target
    return state


def _phase_index(phase_name: str) -> int:
    """Return the index of ``phase_name`` in the canonical PLANNED_PATH.

    Returns ``-1`` if the phase is not on the planned-path
    (e.g. ``BLOCKED``); in that case the resume runner cannot make
    forward progress without external intervention.
    """
    for i, p in enumerate(PLANNED_PATH):
        if p.value == phase_name:
            return i
    return -1


@dataclass
class ResumeRunner:
    """Drives a coach run forward from a reconstructed state.

    The runner is constructed with a ``decision_writer`` (the same
    append-only writer used by the original run; #498 / P001) and an
    optional ``transition_action`` callable that performs the side
    effect for one transition. The runner relies on the writer's
    decision-id idempotency to skip already-logged transitions — so a
    transition's action is only invoked when no record for it exists in
    the durable log yet.
    """

    runtime_dir: Path
    run_id: str
    decision_writer: DecisionWriter
    transition_action: Optional[TransitionAction] = None
    #: Where the gate resolves an approval token from, and the config that says
    #: which edges are gated (#1619). Defaults keep every existing caller working:
    #: ``worktree`` falls back to the cwd, and ``gate_config`` to the repo's
    #: ``.atdd/config.yaml``, so a resume run gates exactly as the CLI does.
    worktree: Optional[Path] = None
    gate_config: Optional[dict] = None
    _watcher: Optional[RuntimeWatcher] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.runtime_dir = Path(self.runtime_dir)

    # ------------------------------------------------------------------
    # State reconstruction
    # ------------------------------------------------------------------

    def reconstruct(self) -> dict[int, str]:
        return reconstruct_state(self.runtime_dir, self.run_id)

    # ------------------------------------------------------------------
    # Watcher reattachment
    # ------------------------------------------------------------------

    def attach_watchers(self) -> tuple[CoachEventQueue, RuntimeWatcher]:
        """Reattach the runtime watcher and replay pending events.

        Marks every event already represented in ``decisions.jsonl`` as
        handled BEFORE replay, so events whose handlers completed are
        not re-emitted. Events that occurred during the kill window
        but whose handlers had not run are delivered now via the
        watcher's ``replay_from_disk()`` machinery.

        Returns the queue and the started watcher; callers are
        responsible for ``watcher.stop()``.
        """
        queue = CoachEventQueue(runtime_dir=self.runtime_dir)
        watcher = RuntimeWatcher(runtime_dir=self.runtime_dir, queue=queue)
        self._mark_handled_from_decisions(watcher)
        watcher.replay_from_disk()
        watcher.persist_checkpoint()
        watcher.start()
        self._watcher = watcher
        return queue, watcher

    def _mark_handled_from_decisions(self, watcher: RuntimeWatcher) -> None:
        """Tell the watcher to suppress events whose handlers already
        completed.

        The mapping from decision → event natural-key is governed by
        the decision's ``inputs`` payload. Decisions emitted by handlers
        for a given ``event_type`` use input keys that mirror that
        type's natural-key tuple from ``event_queue.NATURAL_KEY``.
        """
        for rec in read_decisions(self.runtime_dir, self.run_id):
            event = self._decision_to_event(rec)
            if event is None:
                continue
            watcher.mark_handled(event)

    @staticmethod
    def _decision_to_event(rec: dict) -> Optional[dict]:
        """Best-effort recovery of an event-shaped dict from a decision
        record so the watcher's natural-key index can recognize it.

        Returns ``None`` when the decision does not correspond to a
        handled event (e.g. ``worktree-create``, ``agent-spawn`` write
        their own events but those are emitted directly by coach, not
        handled-by-coach).
        """
        dtype = rec.get("decision_type") or ""
        inputs = rec.get("inputs") or {}
        if dtype.startswith("commit-"):
            event_type = "commit_observed"
        elif dtype in NATURAL_KEY:
            event_type = dtype
        else:
            return None
        # Build a synthetic event using the inputs payload. We lift the
        # natural-key fields back into the event shape: top-level keys
        # land at the top level, ``payload.X`` keys land in payload.
        ev: dict = {"event_type": event_type, "payload": {}}
        keys = NATURAL_KEY.get(event_type, ())
        for key in keys:
            if key.startswith("payload."):
                pkey = key.split(".", 1)[1]
                if pkey in inputs:
                    ev["payload"][pkey] = inputs[pkey]
            else:
                if key in inputs:
                    ev[key] = inputs[key]
        return ev

    # ------------------------------------------------------------------
    # Driving forward
    # ------------------------------------------------------------------

    def drive_to_complete(self, issue_numbers: list[int]) -> dict[int, str]:
        """Walk each issue from its reconstructed phase to COMPLETE.

        For every transition along ``PLANNED_PATH``, we consult the
        durable log via ``transactional_decision``: if a record for the
        transition already exists the action is skipped (this is the
        consumer side of P001's idempotency contract); otherwise the
        action is invoked and a new record is appended.

        Returns the final phase per issue.
        """
        reconstructed = self.reconstruct()
        final: dict[int, str] = {}

        for issue in issue_numbers:
            phase_name = reconstructed.get(issue, Phase.INIT.value)
            if _phase_index(phase_name) < 0:
                # BLOCKED or unknown; the resume runner cannot make
                # forward progress without operator action. Leave the
                # phase as-is and continue with siblings.
                final[issue] = phase_name
                continue
            final[issue] = self._walk_forward(issue, phase_name)

        return final

    def _walk_forward(self, issue: int, start_phase: str) -> str:
        """Advance one issue along ``PLANNED_PATH`` as far as it legitimately can.

        Returns the phase it came to rest at. Stops on the first step that is off
        the path, illegal per the phase machine, or REFUSED BY THE GATE — the
        three are deliberately the same kind of stop (#1619): ``can_transition``
        answers phase-machine LEGALITY, never whether the edge's gates are green,
        so a walk that consulted only it would drive straight past a gate that
        said no. The run keeps whatever it legally AND legitimately earned, and
        nothing is forced.
        """
        current = start_phase
        while current != Phase.COMPLETE.value:
            idx = _phase_index(current)
            if idx < 0 or idx + 1 >= len(PLANNED_PATH):
                break
            next_phase = PLANNED_PATH[idx + 1]
            # Stop walking past COMPLETE — MERGED is owned by the
            # PR-merge handler, not the per-issue resume runner.
            if next_phase == Phase.MERGED:
                break
            if not can_transition(Phase(current), next_phase):
                break
            if not self._step_transition(issue, current, next_phase.value):
                break
            current = next_phase.value
        return current

    def _step_transition(self, issue: int, src: str, dst: str) -> bool:
        """Drive one step. Returns True if the phase advanced, False if refused.

        #1619: returns a verdict rather than None so ``drive_to_complete`` can
        stop the walk on a refusal instead of driving on past a gate that said no.
        """
        record = {
            "decision_id": _phase_transition_decision_id(self.run_id, issue, src, dst),
            "timestamp": _now(),
            "coach_run_id": self.run_id,
            "issue_number": issue,
            "decision_type": "phase-transition",
            "inputs": {"current_phase": src, "target_phase": dst},
            "outcome": {"transitioned": True, "new_phase": dst},
        }
        # Idempotent replay: a transition already in the durable log is a
        # no-op — the consumer side of P001's idempotency contract. Already
        # recorded means already earned, so the walk continues past it.
        if self.decision_writer.has_decision(record["decision_id"]):
            return True
        # The enforcing gate (#1619). Evaluated BEFORE the transition_action
        # guard below: a gated edge with no approval token must refuse whether or
        # not orchestration happens to be wired, and reporting "no
        # transition_action" for an edge that was never going to be allowed would
        # name the wrong obstacle.
        if not self._gate_allows(issue, src, dst):
            return False
        # A resume run with pending phases MUST have a real transition_action.
        # Without one the runner would paper-stamp the phase to COMPLETE with
        # no persona spawn and no orchestration — the #734 / #662 paper fast-
        # forward bug. Fail loudly *before* writing any record.
        if self.transition_action is None:
            raise RuntimeError(
                f"ResumeRunner cannot drive #{issue} {src}->{dst}: no "
                f"transition_action is wired. A resume run with pending phases "
                f"requires a transition_action that performs real "
                f"orchestration; refusing to paper-stamp the transition."
            )
        # Run the action FIRST. Only a transition whose orchestration genuinely
        # completed is durably recorded — a failed phase raises and writes no
        # record, so the next resume re-runs it instead of skipping past a
        # paper stamp.
        self.transition_action(issue, src, dst)
        self.decision_writer.append(record)
        return True

    def _gate_allows(self, issue: int, src: str, dst: str) -> bool:
        """Evaluate the enforcing transition gate for one step (#1619).

        On refusal, records the refusal and returns False. The record is
        DELIBERATELY not ``decision_type: "phase-transition"``:
        :func:`reconstruct_state` rebuilds each issue's phase from every such
        record's ``inputs.target_phase``, so writing a refusal under that type
        would make the next resume reconstruct the refused phase as REACHED and
        skip past a transition that never happened — a paper fast-forward
        laundered through the durable log, which is the #734/#662 bug this runner
        already refuses to commit directly.
        """
        from atdd.coach.gate.decision import GateContext
        from atdd.coach.gate.enforcement import enforce_transition_gate

        worktree = Path(self.worktree) if self.worktree is not None else Path.cwd()
        outcome = enforce_transition_gate(
            self._resolve_gate_config(worktree),
            GateContext(
                issue_number=issue, from_phase=src, to_phase=dst, worktree=worktree
            ),
        )
        if outcome.proceed:
            return True

        reasons = [f"[{b.gate_id} / {b.rule_id}] {b.message}" for b in outcome.blockers]
        print(
            f"#{issue}: resume stopped at {dst} — the transition gate refused "
            f"{src}->{dst} ({len(outcome.blockers)} check(s) blocked). The store "
            f"keeps whatever it legitimately earned so far, and nothing was forced."
        )
        for reason in reasons:
            print(f"  ✗ {reason}")
        self.decision_writer.append({
            "decision_id": (
                f"{_phase_transition_decision_id(self.run_id, issue, src, dst)}"
                f":refused"
            ),
            "timestamp": _now(),
            "coach_run_id": self.run_id,
            "issue_number": issue,
            "decision_type": "phase-transition-refused",
            "inputs": {"current_phase": src, "proposed_phase": dst},
            "outcome": {"transitioned": False, "blockers": reasons},
        })
        return False

    def _resolve_gate_config(self, worktree: Path) -> dict:
        """The ``gate.transitions`` config this run is held to.

        An explicit ``gate_config`` wins; otherwise the worktree's own
        ``.atdd/config.yaml``, so a resume run gates exactly as the CLI does in
        that repo. An unreadable or absent config yields ``{}``, which leaves
        ``DEFAULT_GATED_TRANSITIONS`` in charge — the consumer-repo default, and
        fail-closed in the sense that matters: it gates MORE, never less.
        """
        if self.gate_config is not None:
            return self.gate_config
        import yaml

        path = Path(worktree) / ".atdd" / "config.yaml"
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            # Observably react, never merely return: an unreadable config silently
            # becoming "the defaults" is how a repo's chosen gate posture
            # disappears without anyone being told.
            logger.warning(
                "gate config unreadable; falling back to the built-in "
                "gated-transition defaults",
                extra={"path": str(path), "error": str(exc)},
            )
            print(
                f"[resume] .atdd/config.yaml at {path} is unreadable ({exc}); "
                f"falling back to the built-in gated-transition defaults",
                file=sys.stderr,
            )
            return {}
