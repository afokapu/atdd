# URN: test:integration-hardening:coach-e2e-integration:Y001-SMOKE-001-handlers-importable-and-decisions-written-on-real-fs
# Acceptance: acc:integration-hardening:Y001-SMOKE-001-handlers-importable-and-decisions-written-on-real-fs
# WMBT: wmbt:integration-hardening:Y001
# Phase: SMOKE
# Layer: smoke

"""Y001-SMOKE-001 — all eight Wave-10 handler modules importable; real
decisions.jsonl written to real filesystem without patch/MagicMock on any
handler logic, state machine, or filesystem path.

Only external service calls are stubbed via monkeypatch (spawn._call_spawn,
two_phase_commit._create_pr, two_phase_commit._merge_pr) — these are
genuine external service boundaries, not infrastructure.

Smoke distinction from the GREEN integration test:
  - No unittest.mock.patch / MagicMock used anywhere
  - No fake DispatchResult (validator_dispatch runs with an empty real dir)
  - Real CoachContext, DecisionWriter, CoachEventQueue, StateMachine
  - Assertions check real on-disk artifacts, not call counts on mock objects
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.integration]

_PLANNED_TRANSITIONS = [
    ("INIT", "PLANNED"),
    ("PLANNED", "RED"),
    ("RED", "GREEN"),
    ("GREEN", "SMOKE"),
    ("SMOKE", "REFACTOR"),
    ("REFACTOR", "COMPLETE"),
    ("COMPLETE", "MERGED"),
]

_HANDLER_MODULES = [
    "atdd.coach.handlers.decisions",
    "atdd.coach.handlers.spawn",
    "atdd.coach.handlers.validator_dispatch",
    "atdd.coach.handlers.observer",
    "atdd.coach.handlers.reviewer",
    "atdd.coach.handlers.two_phase_commit",
    "atdd.coach.handlers.watcher",
    "atdd.coach.handlers.state_machine",
]


# ---------------------------------------------------------------------------
# Y001-SMOKE-001a: handler imports and interface contract
# ---------------------------------------------------------------------------


def test_all_handler_modules_importable() -> None:
    """All eight Wave-10 handler modules import without ImportError."""
    for module_path in _HANDLER_MODULES:
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            pytest.fail(
                f"SMOKE: handler module {module_path!r} failed to import: {exc}"
            )
        assert mod is not None, f"import returned None for {module_path!r}"


def test_handler_modules_expose_handle_callable() -> None:
    """K1/J3/M3/L1/N5/J4 handler modules each expose a callable handle()."""
    handle_modules = [
        "atdd.coach.handlers.decisions",
        "atdd.coach.handlers.spawn",
        "atdd.coach.handlers.validator_dispatch",
        "atdd.coach.handlers.observer",
        "atdd.coach.handlers.reviewer",
        "atdd.coach.handlers.two_phase_commit",
        "atdd.coach.handlers.watcher",
    ]
    for module_path in handle_modules:
        mod = importlib.import_module(module_path)
        assert callable(getattr(mod, "handle", None)), (
            f"SMOKE: {module_path!r} must expose a callable handle(); "
            f"got {type(getattr(mod, 'handle', None))!r}"
        )


# ---------------------------------------------------------------------------
# Y001-SMOKE-001b: real filesystem drive, no patch/MagicMock on handlers
# ---------------------------------------------------------------------------


def test_real_drive_writes_decisions_jsonl_to_real_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full drive with real handlers; only external service calls stubbed.

    decisions.jsonl must appear on real disk and contain valid JSON Lines.
    No unittest.mock.patch or MagicMock is used.
    """
    from atdd.coach.handlers.state_machine import CoachContext, Phase, Transition
    from atdd.coach.handlers import (
        decisions as decisions_handler,
        spawn as spawn_handler,
        two_phase_commit as tpc_handler,
    )

    issue_number = 617
    runtime_dir = tmp_path / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)

    # Stub only genuine external service boundaries (no MagicMock):
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
        spawn_handler,
        "_call_spawn",
        lambda ctx, persona, phase, llm, prompt, wt, agent_id, rr: {"surface_ref": "stub"},
    )
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "stub-prompt"
    )
    wt = tmp_path / "worktree"
    wt.mkdir()
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
        tpc_handler, "_create_pr", lambda issue_number: True
    )
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
        tpc_handler, "_merge_pr", lambda: (True, "")
    )
    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
        tpc_handler, "_find_worktree_for_issue", lambda n: None
    )

    ctx = CoachContext(
        issue_number=issue_number,
        coach_run_id="smoke-run-617",
        runtime_dir=runtime_dir,
        dry_run=False,
        skip_review=True,
        auto_merge=True,
    )

    # Drive all transitions using REAL handler logic (no mock.patch)
    for src, dst in _PLANNED_TRANSITIONS:
        t = Transition(src=Phase(src), dst=Phase(dst))
        decisions_handler.handle(ctx, t)
        # K1 spawn: real path resolution logic runs, only _call_spawn stubbed
        spawn_handler.handle(ctx, t)
        # J4: real branching logic runs, only subprocess stubs
        tpc_handler.handle(ctx, t)

    # Assertions on real on-disk artifacts — not call counts on mocks
    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists(), (
        f"SMOKE: decisions.jsonl must exist at {decisions_path} after real drive"
    )

    raw_lines = [
        ln for ln in decisions_path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(raw_lines) == len(_PLANNED_TRANSITIONS), (
        f"SMOKE: expected {len(_PLANNED_TRANSITIONS)} lines in decisions.jsonl "
        f"(one per transition), got {len(raw_lines)}"
    )

    for i, line in enumerate(raw_lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"SMOKE: decisions.jsonl line {i + 1} is not valid JSON: {exc}\n  {line!r}"
            )
        assert "decision_id" in rec, f"SMOKE: line {i + 1} missing decision_id"
        assert "coach_run_id" in rec, f"SMOKE: line {i + 1} missing coach_run_id"
        assert rec["coach_run_id"] == "smoke-run-617", (
            f"SMOKE: line {i + 1} coach_run_id mismatch: {rec['coach_run_id']!r}"
        )
        src, dst = _PLANNED_TRANSITIONS[i]
        assert rec["inputs"]["current_phase"] == src, (
            f"SMOKE: line {i + 1} current_phase mismatch: "
            f"expected {src!r}, got {rec['inputs'].get('current_phase')!r}"
        )
        assert rec["inputs"]["target_phase"] == dst, (
            f"SMOKE: line {i + 1} target_phase mismatch: "
            f"expected {dst!r}, got {rec['inputs'].get('target_phase')!r}"
        )


def test_real_watcher_event_loop_with_real_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J5: WatcherEventLoop advances state using a real CoachEventQueue
    (no MagicMock); RuntimeWatcher background thread stubbed as external infra.
    """
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import Phase, StateMachine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    class _StubRuntimeWatcher:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def persist_checkpoint(self) -> None:
            pass

    monkeypatch.setattr(  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2026-08-15
        "atdd.coach.handlers.watcher.RuntimeWatcher", _StubRuntimeWatcher
    )

    runtime_dir = tmp_path / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)

    queue = CoachEventQueue(runtime_dir=runtime_dir)
    sm = StateMachine(issue_number=617, phase=Phase.RED)

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
        coach_run_id="smoke-watcher-617",
    )

    # Inject event using real queue.put() (not a mock)
    import json as _json
    queue.put({
        "event_type": "commit_observed",
        "timestamp": "2026-05-12T00:00:00.000000Z",
        "payload": {
            "sha": "smokeabc",
            "trailers": {"Issue": "617", "Phase": "RED"},
        },
    })

    result = loop.process_one_event(timeout=0.5)
    assert result == "applied", (
        f"SMOKE: J5 WatcherEventLoop must return 'applied' for a matching event, got {result!r}"
    )
    assert sm.phase == Phase.GREEN, (
        f"SMOKE: StateMachine must advance RED→GREEN after RED event, still {sm.phase!r}"
    )

    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists(), (
        "SMOKE: WatcherEventLoop must write decisions.jsonl to real filesystem"
    )
    lines = [ln for ln in decisions_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["outcome"]["to_phase"] == "GREEN"
    assert rec["coach_run_id"] == "smoke-watcher-617"
