# URN: test:govern-lifecycle:enforcing-phase-transition-gate:R011-INTEGRATION-001-every-phase-advancing-path-consults-the-seam
# Acceptance: acc:govern-lifecycle:R011-INTEGRATION-001-every-phase-advancing-path-consults-the-seam
# WMBT: wmbt:govern-lifecycle:R011
# Phase: RED
# Layer: integration
# Assertion: behavioral
# Purpose: every path that can advance an issue's phase evaluates the gate through the one seam, and deleting any single call turns this RED naming the path that lost its gate
"""R011-INTEGRATION-001 — the wiring guard, one entry per phase-advancing path.

#1619 enumerated four phase-advancing paths reaching the gate through THREE call
sites: programmatic ``IssueLifecycle.transition``, the ``issue_reconcile_state``
replay and the CLI verb all funnel through ``issue_transition.apply_transition``
-> ``IssueLifecycle._transition_gate``; ``resume.py`` and ``handlers/watcher.py``
each need a call site that does not exist today.

Wiring is exactly what rots silently — deleting one call is a one-line edit no
other test in the repo would notice. This file is the per-path equivalent of
``test_smoke_execution_gate_binding.py``, which already guards the #1602
registrar the same way and for the same reason.

Two halves, deliberately:

* STRUCTURAL — each site is read as SOURCE, because a call is a statement, not a
  value; only reading it can tell whether it is still there. Each assertion names
  its path, so a failure says which road lost its gate rather than "something
  broke".
* BEHAVIOURAL — each path is exercised on a gated edge with no token and must
  actually refuse. Structure alone would pass a call that ignores its result.

RED state: ``atdd.coach.gate.enforcement`` does not exist and no path calls it.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.platform]

_PKG = Path(atdd.__file__).resolve().parent

#: The function every phase-advancing path must route its decision through.
_SEAM = "enforce_transition_gate"

#: path label -> module that must call the seam before advancing a phase.
_PHASE_ADVANCING_SITES = {
    "transition chokepoint (CLI verb + programmatic transition + reconcile replay)":
        _PKG / "coach" / "commands" / "issue_lifecycle.py",
    "resume runner PLANNED_PATH walk":
        _PKG / "coach" / "commands" / "resume.py",
    "watcher event loop":
        _PKG / "coach" / "handlers" / "watcher.py",
}

_ISSUE = 999013
_GATED_CONFIG = {"gate": {"transitions": {"PLANNED->RED": True}}}

#: The watcher drives only RED/GREEN/SMOKE/REFACTOR (``watcher._ADVANCE_FROM``),
#: so its acceptance gates an edge it can actually propose. See the comment in
#: the watcher test for why gating PLANNED->RED there would be vacuous.
_WATCHER_GATED_CONFIG = {"gate": {"transitions": {"RED->GREEN": True}}}


def _calls(path: Path, func_name: str) -> bool:
    """True iff ``path``'s source contains a call to ``func_name``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == func_name:
            return True
    return False


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# --------------------------------------------------------------------------- #
# Structural: the wiring exists, per path                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "label,module", sorted(_PHASE_ADVANCING_SITES.items()), ids=lambda v: v if isinstance(v, str) else ""
)
def test_phase_advancing_path_calls_the_enforcement_seam(label: str, module: Path):
    """R011-INTEGRATION-001: every path evaluates the gate through the seam."""
    assert module.exists(), f"{label}: {module} is gone — the guard needs repointing"
    assert _calls(module, _SEAM), (
        f"{label} no longer calls {_SEAM}() — this path can advance an issue's "
        f"phase across a gated edge without the gate ever looking, which is the "
        f"exact defect #1619 exists to close. Restore the call in {module.name}."
    )


def test_the_empty_registry_fail_open_is_gone_from_the_transition_chokepoint():
    """R011-INTEGRATION-001: fail-open A is deleted, not merely bypassed.

    Asserted over the AST, not over the file's text. A substring search also
    matches the prose explaining that the branch was removed, so it would fail on
    a correct fix that documents itself — which is exactly what it did on first
    run. What must be absent is the CALL, not the words.
    """
    tree = ast.parse(
        (_PKG / "coach" / "commands" / "issue_lifecycle.py").read_text(encoding="utf-8")
    )
    empty_checks = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "is_empty"
        and getattr(getattr(node.func, "value", None), "id", None) == "GATE_REGISTRY"
    ]
    assert not empty_checks, (
        "issue_lifecycle._transition_gate still short-circuits on an empty "
        "registry (GATE_REGISTRY.is_empty() called at line(s) "
        f"{[n.lineno for n in empty_checks]}). That branch IS the fail-open "
        "(#1619 fail-open A): it converts a missing registration into a silent "
        "pass. The seam now guarantees registration ran, so the branch has "
        "nothing left to protect."
    )


def test_the_registry_no_longer_depends_on_which_verb_ran():
    """R011-INTEGRATION-001: registration is unbound from the CLI verb dispatch.

    Root cause fact one. Leaving the verb-bound calls in place beside the seam
    would leave the misleading binding in the source and make the fix look
    optional (Decision 7).
    """
    verb = _PKG / "coach" / "commands" / "issue_transition.py"
    assert not _calls(verb, "register_approval_checks"), (
        "issue_transition still registers at the verb dispatch; the registry's "
        "contents must depend on the edge being crossed, not on how the caller "
        "was invoked"
    )
    assert not _calls(verb, "register_smoke_execution_check"), (
        "issue_transition still registers the #1602 check at the verb dispatch"
    )


# --------------------------------------------------------------------------- #
# Behavioural: the wiring is load-bearing, per path                            #
# --------------------------------------------------------------------------- #


def test_watcher_refuses_a_gated_edge_and_records_the_refusal(tmp_path: Path):
    """R011-INTEGRATION-001: the watcher does not mutate the machine on refusal.

    Decision 5, adjudicated: RECORD AND REFUSE. The synchronous paths have a
    caller who receives a non-zero exit and a printed reason; the watcher has
    none, so a silent no-op would make a GATED event indistinguishable from an
    IGNORED one — the same defect class as the fail-open, an absence that reads
    as a normal outcome.

    The refusal record must NOT be ``decision_type: "phase-transition"``:
    ``resume.reconstruct_state`` treats every such record's ``inputs.target_phase``
    as a reached phase, so reusing the type would make a refusal reconstruct as an
    ADVANCE — a paper fast-forward laundered through the durable log, which is the
    #734/#662 bug the resume runner already refuses to commit directly.
    """
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import Phase, initialize_state_machine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    runtime_dir = tmp_path / "runtime"
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = initialize_state_machine(issue_number=_ISSUE)
    # RED->GREEN, not PLANNED->RED: `watcher._ADVANCE_FROM` maps only RED, GREEN,
    # SMOKE and REFACTOR, so a `Phase: PLANNED` trailer proposes NO transition and
    # the event is ignored before any gate could be consulted. Gating an edge the
    # watcher cannot drive would make this test pass while proving nothing — it is
    # the "refused for the wrong reason" trap one file over. RED->GREEN is in
    # `registrations._CANDIDATE_TRANSITIONS`, so the approval check covers it.
    sm.phase = Phase.RED

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
        worktree=tmp_path,                 # no approval token lives here
        gate_config=_WATCHER_GATED_CONFIG,  # RED->GREEN is gated
    )

    queue.put({
        "event_type": "commit_observed",
        "agent_id": None,
        "timestamp": "2026-08-03T12:00:00.000000Z",
        "payload": {
            "sha": "deadbeef", "parent_sha": None, "branch": "feat/x",
            "worktree_path": str(tmp_path), "author": "t <t@e.com>",
            "trailers": {"Issue": str(_ISSUE), "Phase": "RED"},
        },
    })
    verdict = loop.process_one_event(timeout=1.0)

    assert verdict == "refused", (
        f"the event must be reported as REFUSED, distinctly from 'ignored' (no "
        f"machine wanted it) and 'applied' (it happened); got {verdict!r}. If this "
        f"is 'ignored', the fixture proposed no transition and the gate was never "
        f"reached — the test would then prove nothing."
    )
    assert sm.phase is Phase.RED, (
        "the watcher advanced the state machine across a gated edge with no "
        "approval token — before #1619 it evaluated no gate on this path at all"
    )

    records = _read_jsonl(runtime_dir / "coach" / "decisions.jsonl")
    advanced = [r for r in records if r.get("decision_type") == "phase-transition"]
    assert not advanced, (
        "a refused transition must not be recorded as a phase-transition; "
        "resume.reconstruct_state would replay it as a reached phase"
    )
    refused = [r for r in records if r.get("decision_type") == "phase-transition-refused"]
    assert len(refused) == 1, (
        f"the refusal must be recorded — an asynchronous refusal nobody records "
        f"is indistinguishable from an ignored event; got {records}"
    )
    assert refused[0]["outcome"].get("transitioned") is False


def test_resume_walk_refuses_a_gated_edge_and_advances_nothing(tmp_path: Path):
    """R011-INTEGRATION-001: the PLANNED_PATH walk consults gates, not only legality.

    ``resume.py`` ships today and walks ``PLANNED_PATH`` end to end, consulting
    ``can_transition`` — phase-machine LEGALITY, not gates. Its existing guard
    refuses to paper-stamp when no ``transition_action`` is wired, but that guards
    ORCHESTRATION BEING PRESENT, not GATES BEING GREEN.
    """
    from atdd.coach.commands.durability import DecisionWriter
    from atdd.coach.commands.resume import ResumeRunner

    runtime_dir = tmp_path / "runtime"
    run_id = "run-r011"
    writer = DecisionWriter(runtime_dir=runtime_dir)
    # Seed the log so the runner reconstructs #_ISSUE as sitting at PLANNED.
    writer.append({
        "decision_id": f"{run_id}:#{_ISSUE}:INIT->PLANNED",
        "timestamp": "2026-08-03T11:00:00.000000Z",
        "coach_run_id": run_id,
        "issue_number": _ISSUE,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": "INIT", "target_phase": "PLANNED"},
        "outcome": {"transitioned": True, "new_phase": "PLANNED"},
    })

    invoked: list[tuple[int, str, str]] = []

    def _action(issue: int, src: str, dst: str) -> dict:
        invoked.append((issue, src, dst))
        return {}

    runner = ResumeRunner(
        runtime_dir=runtime_dir,
        run_id=run_id,
        decision_writer=writer,
        transition_action=_action,
        worktree=tmp_path,          # no approval token lives here
        gate_config=_GATED_CONFIG,  # PLANNED->RED is gated
    )
    final = runner.drive_to_complete([_ISSUE])

    assert final[_ISSUE] == "PLANNED", (
        f"the resume walk crossed the gated PLANNED->RED edge with no approval "
        f"token and drove on to {final[_ISSUE]}"
    )
    assert (_ISSUE, "PLANNED", "RED") not in invoked, (
        "the refused transition's orchestration must not run"
    )
    replayed = [
        r for r in _read_jsonl(runtime_dir / "coach" / "decisions.jsonl")
        if r.get("decision_type") == "phase-transition"
        and (r.get("inputs") or {}).get("target_phase") == "RED"
    ]
    assert not replayed, (
        "a refused step must write no phase-transition record — the next resume "
        "would reconstruct RED as reached and skip past a transition that never "
        "happened"
    )
