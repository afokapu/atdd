# URN: test:govern-lifecycle:split-spawn-and-final-purity-sweep:incident-defenses-suite-i3-to-i13
# Source of truth: docs/coach-decomposition.md §9, §13.10 (umbrella #887)
"""Consolidated incident-defense suite — Coach Decomposition §9 / §13.10 (#897).

The closing child (Child 10) requires that **all 13 incident defenses
(I-1 … I-13) have explicit tests in ``tests/incident_defenses/``**
(docs/coach-decomposition.md §13.10 acceptance, umbrella #887).

Coverage map (one assertion home per defense; see §9 table):

| Defense | Owning layer (§9)                          | Test home                              |
|---------|--------------------------------------------|----------------------------------------|
| I-1     | runtime.worktree.ensure_issue_worktree     | test_worktree_safety::test_refuses_bare_dispatch        |
| I-2     | runtime.worktree (pre-flight)              | test_worktree_safety::test_blocks_main_commit           |
| I-3     | train (event-id / runtime baseline)        | this file::test_i3_*                   |
| I-4     | runtime spawn (cmux >=0.64.7 avoidance)    | this file::test_i4_*                   |
| I-5     | coach.core.next_transition (Persona)       | this file::test_i5_* (+ test_core_pure)|
| I-6     | observer (singleton enforced)              | this file::test_i6_* (atdd.observer)   |
| I-7     | train.issue_runner (no-progress TTL)       | this file::test_i7_*                   |
| I-8     | train.issue_runner (decision-before-action)| this file::test_i8_*                   |
| I-9     | runtime.worktree (core.bare=false)         | test_worktree_safety::test_sets_per_worktree_core_bare  |
| I-10    | runtime.agent_control (env_overrides PATH) | this file::test_i10_*                  |
| I-11    | coach.commands.emergency (5-min TTL)       | this file::test_i11_*                  |
| I-12    | train.issue_runner (advance before merge)  | this file::test_i12_*                  |
| I-13    | .atdd/hooks/pre-push (core.bare block)     | this file::test_i13_*                  |

I-1/I-2/I-9 keep their canonical home in ``test_worktree_safety.py``; this
module pins the remaining ten so the suite is complete and each defense has a
named, executable test that exercises its owning layer's real behavior.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# I-3 — Stale done.json baseline detection
#       Owning layer: train runtime watcher records pre-existing runtime files
#       as already-seen so a prior run's done.json never advances a fresh phase.
# --------------------------------------------------------------------------- #
def test_i3_stale_done_json_is_baselined_not_replayed(tmp_path):
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.commands.runtime_watcher import RuntimeWatcher

    agent_dir = tmp_path / "agents" / "agent-1"
    agent_dir.mkdir(parents=True)
    # A `done.json` left by a PRIOR coach run.
    (agent_dir / "done.json").write_text('{"status": "done", "run": "stale"}\n')

    queue = CoachEventQueue(runtime_dir=tmp_path)
    watcher = RuntimeWatcher(runtime_dir=tmp_path, queue=queue)

    # Baseline at dispatch time records the stale file as already-seen (#711).
    watcher.baseline()
    watcher.scan_once()

    assert len(queue) == 0, "stale done.json must not be replayed as a new agent_done event (I-3)"


def test_i3_post_baseline_done_json_does_emit(tmp_path):
    """Sanity: a done.json written AFTER baseline is a real completion signal."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.commands.runtime_watcher import RuntimeWatcher

    agent_dir = tmp_path / "agents" / "agent-1"
    agent_dir.mkdir(parents=True)

    queue = CoachEventQueue(runtime_dir=tmp_path)
    watcher = RuntimeWatcher(runtime_dir=tmp_path, queue=queue)
    watcher.baseline()  # no done.json yet

    (agent_dir / "done.json").write_text('{"status": "done", "run": "fresh"}\n')
    watcher.scan_once()

    events = queue.drain()
    assert any(e.get("event_type") == "agent_done" for e in events), (
        "a post-dispatch done.json must emit agent_done (I-3 must not over-suppress)"
    )


# --------------------------------------------------------------------------- #
# I-4 — cmux broken-pipe avoidance on >=0.64.7
#       The deprecated new-workspace / new-pane RPCs (which fail with
#       "Broken pipe (errno 32)") are refused before they reach cmux.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("deprecated_mode", ["workspace", "pane"])
def test_i4_deprecated_multiplexer_mode_refused(deprecated_mode, tmp_path):
    from atdd.coach.commands.spawn import (
        DeprecatedMultiplexerModeError,
        _create_surface,
    )

    with pytest.raises(DeprecatedMultiplexerModeError):
        _create_surface(
            object(),  # multiplexer never reached — raises before use
            worktree=tmp_path,
            command="claude",
            name="agent-1",
            mode=deprecated_mode,
        )


# --------------------------------------------------------------------------- #
# I-5 — Persona materialization check (coach.core, pure)
#       next_transition returns the phase_machine's persona for the phase, so a
#       phase can never dispatch the wrong persona.
# --------------------------------------------------------------------------- #
def test_i5_persona_matches_phase_machine_agent():
    from atdd.coach.core import next_transition
    from atdd.coach.core.types import (
        CiState,
        Conventions,
        Evidence,
        IssueType,
        Persona,
        Phase,
        PhaseSpec,
    )

    specs = {
        Phase.INIT: (Persona.PLANNER, (Phase.PLANNED, Phase.BLOCKED)),
        Phase.PLANNED: (Persona.TESTER, (Phase.RED, Phase.BLOCKED)),
        Phase.RED: (Persona.CODER, (Phase.GREEN, Phase.BLOCKED)),
    }
    phase_machine = {
        phase: PhaseSpec(name=phase, agent=agent, transitions_to=trans, pre_commit_gate=None)
        for phase, (agent, trans) in specs.items()
    }
    conv = Conventions(
        phase_machine=phase_machine,
        rules={},
        prompt_templates={},
        snapshot_hash="sha256:test-fixture",
        snapshot_paths=("phase_machine.convention.yaml",),
    )

    def _evidence(phase: Phase) -> Evidence:
        return Evidence(
            issue_number=1, issue_type=IssueType.IMPLEMENTATION, current_phase=phase,
            train_id="0001", branch="feat/x", wmbts=(), validator_reports=(),
            ci_state=CiState.SUCCESS, pr_state=None, last_commit_sha="0" * 40,
            artifacts_present=frozenset(), elapsed_in_phase_seconds=1,
            conventions_hash="sha256:test-fixture",
        )

    for phase in specs:
        decision = next_transition(_evidence(phase), conv)
        assert decision.persona is conv.phase_machine[phase].agent, (
            f"phase {phase} dispatched the wrong persona (I-5)"
        )


# --------------------------------------------------------------------------- #
# I-6 — Single observer lifecycle (atdd.observer singleton)
#       Two observers can never disagree about / race on the surfaced stream.
# --------------------------------------------------------------------------- #
def test_i6_observer_session_is_singleton(tmp_path):
    from atdd.observer import ObserverAlreadyRunningError, ObserverSession

    ObserverSession._active = None
    try:
        first = ObserverSession(tmp_path).start()
        with pytest.raises(ObserverAlreadyRunningError):
            ObserverSession(tmp_path).start()
        first.stop()
        # slot released → a fresh session may start
        ObserverSession(tmp_path).start().stop()
    finally:
        ObserverSession._active = None


# --------------------------------------------------------------------------- #
# I-7 — No-progress TTL escalation (train.issue_runner helper)
# --------------------------------------------------------------------------- #
def test_i7_no_progress_ttl_escalates(tmp_path, monkeypatch):
    from atdd.coach.commands import coach as coach_mod
    from atdd.coach.core.types import Phase

    escalations: list[str] = []
    monkeypatch.setattr(
        coach_mod, "_write_escalation",
        lambda channel, message: escalations.append(message),
    )

    # last advance 600s ago, TTL 300s → must escalate and signal self-terminate.
    fired = coach_mod._check_no_progress_ttl(
        last_advance_at=time.monotonic() - 600.0,
        no_progress_ttl_seconds=300,
        escalation_channel="stub",
        issue_number=4242,
        current_phase=Phase.RED,
    )
    assert fired is True, "TTL exceeded must return True (self-terminate) (I-7)"
    assert escalations and "no progress" in escalations[0]


def test_i7_within_ttl_does_not_escalate(monkeypatch):
    from atdd.coach.commands import coach as coach_mod
    from atdd.coach.core.types import Phase

    monkeypatch.setattr(coach_mod, "_write_escalation",
                        lambda *a, **k: pytest.fail("must not escalate within TTL"))
    fired = coach_mod._check_no_progress_ttl(
        last_advance_at=time.monotonic(),
        no_progress_ttl_seconds=300,
        escalation_channel="stub",
        issue_number=4242,
        current_phase=Phase.RED,
    )
    assert fired is False


# --------------------------------------------------------------------------- #
# I-8 — Durable decision-before-action (train durability contract)
#       transactional_decision appends the decision BEFORE the side-effecting
#       body runs, and re-running with the same decision_id is a no-op.
# --------------------------------------------------------------------------- #
def test_i8_decision_persisted_before_action(tmp_path):
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    writer = DecisionWriter(runtime_dir=tmp_path)
    record = {
        "decision_id": "run-1:#42:RED->GREEN",
        "timestamp": "2026-05-31T00:00:00Z",
        "coach_run_id": "run-1",
        "issue_number": 42,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": "RED", "target_phase": "GREEN"},
        "outcome": {"transitioned": True, "new_phase": "GREEN"},
    }

    with transactional_decision(writer, record) as proceed:
        assert proceed is True
        # At the moment the body runs (the side effect), the decision is
        # already durably recorded — that is the resume contract (I-8).
        assert writer.has_decision(record["decision_id"]), (
            "decision must be persisted BEFORE the action body runs (I-8)"
        )

    # Idempotent replay: same decision_id → skip the action, no double-execute.
    with transactional_decision(writer, record) as proceed_again:
        assert proceed_again is False, "replayed decision must not re-run the action (I-8)"


def test_i8_decision_durable_even_if_body_raises(tmp_path):
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    writer = DecisionWriter(runtime_dir=tmp_path)
    record = {
        "decision_id": "run-1:#43:GREEN->SMOKE",
        "timestamp": "2026-05-31T00:00:00Z",
        "coach_run_id": "run-1",
        "issue_number": 43,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": "GREEN", "target_phase": "SMOKE"},
        "outcome": {"transitioned": True, "new_phase": "SMOKE"},
    }

    with pytest.raises(RuntimeError):
        with transactional_decision(writer, record):
            raise RuntimeError("action blew up after decision was recorded")

    assert writer.has_decision(record["decision_id"]), (
        "a crash in the action body must not lose the durable decision (I-8)"
    )


# --------------------------------------------------------------------------- #
# I-10 — Forbidden-command guard via DispatchSpec.env_overrides (PATH shim)
#        runtime.agent_control threads env_overrides (e.g. PATH=.atdd/bin:...)
#        into the worker dispatch command. The git PATH-shim itself ships in
#        #884; here we pin the runtime mechanism that delivers it.
# --------------------------------------------------------------------------- #
def test_i10_env_overrides_threaded_into_dispatch(tmp_path):
    from atdd.coach.commands.spawn import _prepend_env_prefix
    from atdd.runtime.agent_control import DispatchSpec

    shimmed_path = f"{tmp_path / '.atdd' / 'bin'}{os.pathsep}/usr/bin"
    # #979: the legacy shim --env delivery was removed; the sole cmux-native
    # launch plane threads DispatchSpec.env_overrides into the surface command
    # as a shell KEY=value prefix (_prepend_env_prefix), so the git PATH shim
    # still reaches the worker process.
    cmd = _prepend_env_prefix(
        "claude --permission-mode default",
        {"PATH": shimmed_path},
    )
    assert cmd.startswith("PATH="), (
        "DispatchSpec.env_overrides must reach the worker as a shell prefix (I-10)"
    )
    assert ".atdd/bin" in cmd, "the shimmed PATH (.atdd/bin first) must be delivered (I-10)"

    # And DispatchSpec carries env_overrides as a typed field (§4.8).
    spec = DispatchSpec(
        agent_id="agent-1",
        persona="coder",
        worktree_path=tmp_path,
        prompt_text="go",
        correction_inbox=tmp_path / "cli-return.jsonl",
        output_log=tmp_path / "output.log",
        runtime_dir=tmp_path,
        env_overrides={"PATH": shimmed_path},
        transport="cmux-native",
        permission_mode="default",
        allowed_tools=(),
    )
    assert spec.env_overrides["PATH"] == shimmed_path


# --------------------------------------------------------------------------- #
# I-11 — Emergency bypass: 5-minute TTL + audit log
# --------------------------------------------------------------------------- #
def test_i11_emergency_bypass_writes_audit_and_bypass(tmp_path):
    from atdd.coach.commands.emergency import cmd_emergency

    (tmp_path / ".atdd").mkdir()
    cmd_emergency("installed-validator false-red", repo_root=tmp_path)

    bypass = tmp_path / ".atdd" / "EMERGENCY_BYPASS"
    audit = tmp_path / ".atdd" / "emergency-audit.jsonl"
    assert bypass.is_file(), "emergency bypass file must be written (I-11)"
    assert "reason=installed-validator false-red" in bypass.read_text()
    assert "timestamp=" in bypass.read_text(), "bypass carries mtime/timestamp for the 5-min TTL"
    assert audit.is_file() and audit.read_text().strip(), "every bypass is audit-logged (I-11)"


# --------------------------------------------------------------------------- #
# I-12 — Issue advancement BEFORE partial-PR merge
#        The two-phase-commit handler only ever attempts a merge once the issue
#        has reached COMPLETE; any earlier source phase is a NOOP. This pins the
#        ordering invariant that prevents the post-merge stale-CI race.
# --------------------------------------------------------------------------- #
def test_i12_merge_only_fires_from_complete(monkeypatch):
    from atdd.coach.handlers import two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import (
        CoachContext, HandlerResult, Phase, Transition,
    )

    merge_calls: list[str] = []
    monkeypatch.setattr(tpc, "_create_pr", lambda n: (_ for _ in ()).throw(
        AssertionError("PR/merge must not start before the issue reaches COMPLETE (I-12)")))
    monkeypatch.setattr(tpc, "_merge_pr", lambda: merge_calls.append("merge") or (True, ""))

    ctx = CoachContext(issue_number=42)
    ctx.auto_merge = True
    # A premature transition (not from COMPLETE) must be a NOOP — no merge.
    result = tpc.handle(ctx, Transition(Phase.REFACTOR, Phase.COMPLETE))
    assert result == HandlerResult.NOOP
    assert merge_calls == [], "merge must not run before advancement to COMPLETE (I-12)"


def test_i12_complete_to_merged_runs_create_then_merge(monkeypatch):
    from atdd.coach.handlers import two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import (
        CoachContext, HandlerResult, Phase, Transition,
    )

    order: list[str] = []
    monkeypatch.setattr(tpc, "_create_pr", lambda n: order.append("create") or True)
    monkeypatch.setattr(tpc, "_merge_pr", lambda: (order.append("merge"), (True, ""))[1])
    monkeypatch.setattr(tpc, "_find_worktree_for_issue", lambda n: None)

    ctx = CoachContext(issue_number=42)
    ctx.auto_merge = True
    result = tpc.handle(ctx, Transition(Phase.COMPLETE, Phase.MERGED))

    assert result == HandlerResult.HANDLED
    assert order == ["create", "merge"], "advancement (COMPLETE) precedes the merge (I-12)"


# --------------------------------------------------------------------------- #
# I-13 — Pre-push hook blocks core.bare=true worktrees
# --------------------------------------------------------------------------- #
def test_i13_pre_push_hook_guards_core_bare():
    """The shipped pre-push hook refuses to push when the worktree is core.bare=true."""
    hook = REPO_ROOT / ".atdd" / "hooks" / "pre-push"
    assert hook.is_file(), "pre-push hook must ship (I-13)"
    text = hook.read_text()
    assert "core.bare" in text, "pre-push hook must inspect core.bare (I-13)"
    # The guard must actually block (non-zero exit), not merely warn.
    assert ("exit 1" in text or "exit 2" in text), (
        "pre-push hook must hard-block (non-zero exit) on core.bare=true (I-13)"
    )
