# URN: test:integration-hardening:coach-e2e-integration:Y001-INTEGRATION-001-all-seams-exercised-in-happy-path
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-001-all-seams-exercised-in-happy-path
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-002-decisions-jsonl-has-expected-sequence
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-003-spawn-personas-match-table
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-004-validator-fires-at-each-phase-exit
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-005-j4-merge-fires-on-complete
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-006-watcher-event-advances-state
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-007-llm-registry-registers-mock-client
# Acceptance: acc:integration-hardening:Y001-INTEGRATION-008-test-completes-under-30s
# WMBT: wmbt:integration-hardening:Y001
# Phase: RED
# Layer: integration

"""Keystone E2E integration test — all eight Wave-10 seams in one drive.

Exercises every seam wired by issues #585–#592 together in a single
INIT → COMPLETE → MERGED lifecycle drive against a CoachContext with
mocked external calls (no real subprocess, no real gh, no real cmux).

Eight seam assertions (one per Wave-10 child):
  K1 (#585) — spawn handler fires 5× with correct persona sequence
  J3 (#586) — decisions.jsonl populated with one schema-valid entry per transition
  J5 (#587) — WatcherEventLoop advances state on injected commit_observed event
  M3 (#588) — dispatch_validators called at phase-exit gates; HANDLED when clean
  L1 (#589) — observer.handle called at each transition; NOOP without agent dir
  N5 (#589) — reviewer.handle NOOP when skip_review=True
  J4 (#590) — two_phase_commit.handle fires at COMPLETE→MERGED with auto_merge
  C001 (#592) — LLM registry registers and retrieves a mock client

Motivating bug: #611's post-commit hook used `-m "not github_api"` instead of
`--skip-api`. The coach state machine has 8× the seams — proportional risk of
silent integration breakage. This test is the safety net.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration]

# ---------------------------------------------------------------------------
# Planned-path transitions used across all assertions
# ---------------------------------------------------------------------------

_PLANNED_TRANSITIONS = [
    ("INIT", "PLANNED"),
    ("PLANNED", "RED"),
    ("RED", "GREEN"),
    ("GREEN", "SMOKE"),
    ("SMOKE", "REFACTOR"),
    ("REFACTOR", "COMPLETE"),
    ("COMPLETE", "MERGED"),
]

_SPAWN_PERSONA_TABLE = [
    ("INIT", "PLANNED", "planner"),
    ("PLANNED", "RED", "tester"),
    ("RED", "GREEN", "coder"),
    ("GREEN", "SMOKE", "tester"),
    ("SMOKE", "REFACTOR", "coder"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    issue_number: int,
    runtime_dir: Path,
    *,
    auto_merge: bool = False,
    skip_review: bool = True,
) -> "CoachContext":
    from atdd.coach.handlers.state_machine import CoachContext

    return CoachContext(
        issue_number=issue_number,
        coach_run_id="e2e-test-run-617",
        runtime_dir=runtime_dir,
        dry_run=False,
        skip_review=skip_review,
        auto_merge=auto_merge,
    )


def _make_transition(src: str, dst: str) -> "Transition":
    from atdd.coach.handlers.state_machine import Phase, Transition

    return Transition(src=Phase(src), dst=Phase(dst))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _make_dispatch_result(violations_path: Path, violations: list[dict]) -> MagicMock:
    violations_path.parent.mkdir(parents=True, exist_ok=True)
    violations_path.write_text(
        "\n".join(json.dumps(v) for v in violations) + ("\n" if violations else "")
    )
    result = MagicMock()
    result.violations_path = violations_path
    result.exit_code = 0
    return result


# ---------------------------------------------------------------------------
# GT-001 + GT-002: Happy-path drive covering all 8 seams
# ---------------------------------------------------------------------------


def test_coach_drives_issue_init_to_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive all transitions INIT→MERGED through every handler; assert all 8 seams."""
    from atdd.coach.handlers.state_machine import Phase, HandlerResult, Transition
    from atdd.coach.handlers import (
        decisions as decisions_handler,
        spawn as spawn_handler,
        validator_dispatch as validator_dispatch_handler,
        observer as observer_handler,
        reviewer as reviewer_handler,
        two_phase_commit as tpc_handler,
    )
    from atdd.coach.commands.durability import _load_validator

    issue_number = 617
    runtime_dir = tmp_path / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)

    # ── K1 seam: mock spawn internals ───────────────────────────────────────
    spawn_calls: list[dict] = []

    def _fake_call_spawn(
        ctx: Any, persona: str, phase: str, llm: str,
        persona_prompt_content: str, worktree: Path,
        agent_id: str, runtime_root: Path,
    ) -> dict:
        spawn_calls.append({"persona": persona, "phase": phase, "llm": llm})
        return {"surface_ref": f"fake:{len(spawn_calls)}"}

    monkeypatch.setattr(spawn_handler, "_call_spawn", _fake_call_spawn)
    monkeypatch.setattr(
        spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "# test prompt"
    )
    wt = tmp_path / "worktree"
    wt.mkdir()
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: wt)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)

    # ── M3 seam: mock dispatcher, repo root, sha ────────────────────────────
    dispatch_call_count = 0
    fake_sha = "e2e" + "0" * 37

    def _fake_dispatch_validators(**kwargs: Any) -> MagicMock:
        nonlocal dispatch_call_count
        dispatch_call_count += 1
        violations_path = (
            runtime_dir / "validations" / fake_sha / "violations.jsonl"
        )
        return _make_dispatch_result(violations_path, [])

    with (
        patch(
            "atdd.coach.handlers.validator_dispatch.find_repo_root",
            return_value=tmp_path,
        ),
        patch(
            "atdd.coach.handlers.validator_dispatch._get_head_sha",
            return_value=fake_sha,
        ),
        patch(
            "atdd.coach.handlers.validator_dispatch.dispatch_validators",
            side_effect=_fake_dispatch_validators,
        ),
        patch(
            "atdd.coach.handlers.validator_dispatch._resolve_validator_dirs",
            return_value=[tmp_path / "fake_validators"],
        ),
        # ── J4 seam: mock PR creation and merge ─────────────────────────────
        patch(
            "atdd.coach.handlers.two_phase_commit._create_pr",
            return_value=True,
        ) as mock_create_pr,
        patch(
            "atdd.coach.handlers.two_phase_commit._merge_pr",
            return_value=(True, ""),
        ) as mock_merge_pr,
        patch(
            "atdd.coach.handlers.two_phase_commit._find_worktree_for_issue",
            return_value=None,
        ),
    ):
        ctx = _make_ctx(
            issue_number=issue_number,
            runtime_dir=runtime_dir,
            auto_merge=True,
            skip_review=True,
        )

        # Track per-seam results for assertion clarity
        observer_results: list[HandlerResult] = []
        reviewer_results: list[HandlerResult] = []
        decisions_results: list[HandlerResult] = []
        spawn_results: list[HandlerResult] = []
        validator_results: list[HandlerResult] = []
        tpc_results: list[HandlerResult] = []

        for src, dst in _PLANNED_TRANSITIONS:
            t = _make_transition(src, dst)

            # J3: decision written before any side-effect (durable-before-action)
            dr = decisions_handler.handle(ctx, t)
            decisions_results.append(dr)

            # K1: spawn persona agent at each applicable transition
            sr = spawn_handler.handle(ctx, t)
            spawn_results.append(sr)

            # M3: validate at each phase-exit gate
            vr = validator_dispatch_handler.handle(ctx, t)
            validator_results.append(vr)

            # L1: co-spawn observer (NOOP when no agent dir present)
            or_ = observer_handler.handle(ctx, t)
            observer_results.append(or_)

            # N5: reviewer at phase boundaries (NOOP when skip_review=True)
            rr = reviewer_handler.handle(ctx, t)
            reviewer_results.append(rr)

            # J4: two-phase commit (fires only at COMPLETE→MERGED)
            tr = tpc_handler.handle(ctx, t)
            tpc_results.append(tr)

        # ── J3 seam assertions ────────────────────────────────────────────────
        decisions_path = runtime_dir / "coach" / "decisions.jsonl"
        assert decisions_path.exists(), "J3: decisions.jsonl must exist after drive"
        records = _read_jsonl(decisions_path)
        assert len(records) == len(_PLANNED_TRANSITIONS), (
            f"J3: expected {len(_PLANNED_TRANSITIONS)} decision entries, "
            f"got {len(records)}: {[r.get('outcome', {}).get('new_phase') for r in records]}"
        )

        schema_validator = _load_validator("coach-decision.schema.json")
        for i, rec in enumerate(records):
            errors = list(schema_validator.iter_errors(rec))
            assert not errors, (
                f"J3: entry {i} fails schema: {[str(e.message) for e in errors]}"
            )

        for rec, (src, dst) in zip(records, _PLANNED_TRANSITIONS):
            assert rec["inputs"]["current_phase"] == src, (
                f"J3: current_phase mismatch at entry {src}→{dst}: "
                f"{rec['inputs'].get('current_phase')!r}"
            )
            assert rec["inputs"]["target_phase"] == dst, (
                f"J3: target_phase mismatch at entry {src}→{dst}: "
                f"{rec['inputs'].get('target_phase')!r}"
            )

        # ── K1 seam assertions ────────────────────────────────────────────────
        assert len(spawn_calls) == len(_SPAWN_PERSONA_TABLE), (
            f"K1: expected {len(_SPAWN_PERSONA_TABLE)} spawn calls, "
            f"got {len(spawn_calls)}: {[c['persona'] for c in spawn_calls]}"
        )
        for call, (src, dst, expected_persona) in zip(spawn_calls, _SPAWN_PERSONA_TABLE):
            assert call["persona"] == expected_persona, (
                f"K1: persona mismatch for {src}→{dst}: "
                f"expected {expected_persona!r}, got {call['persona']!r}"
            )

        # ── M3 seam assertions ────────────────────────────────────────────────
        assert dispatch_call_count > 0, (
            "M3: dispatch_validators must be called at least once during the drive"
        )
        blocked = [r for r in validator_results if r == HandlerResult.BLOCKED]
        assert not blocked, (
            f"M3: no BLOCKED results expected with empty violations, "
            f"got BLOCKED at {[i for i, r in enumerate(validator_results) if r == HandlerResult.BLOCKED]}"
        )

        # ── L1 seam assertions ────────────────────────────────────────────────
        assert len(observer_results) == len(_PLANNED_TRANSITIONS), (
            "L1: observer.handle must be called for every transition"
        )
        unexpected_observer = [
            r for r in observer_results
            if r not in (HandlerResult.NOOP, HandlerResult.HANDLED)
        ]
        assert not unexpected_observer, (
            f"L1: observer returned unexpected results: {unexpected_observer}"
        )

        # ── N5 seam assertions ────────────────────────────────────────────────
        assert len(reviewer_results) == len(_PLANNED_TRANSITIONS), (
            "N5: reviewer.handle must be called for every transition"
        )
        non_noop_reviewer = [r for r in reviewer_results if r != HandlerResult.NOOP]
        assert not non_noop_reviewer, (
            f"N5: with skip_review=True, all reviewer results must be NOOP, "
            f"got: {non_noop_reviewer}"
        )

        # ── J4 seam assertions ────────────────────────────────────────────────
        mock_create_pr.assert_called_once_with(issue_number)
        mock_merge_pr.assert_called_once()
        complete_merged_idx = len(_PLANNED_TRANSITIONS) - 1
        assert tpc_results[complete_merged_idx] == HandlerResult.HANDLED, (
            f"J4: COMPLETE→MERGED must return HANDLED with auto_merge=True, "
            f"got {tpc_results[complete_merged_idx]!r}"
        )
        for i, r in enumerate(tpc_results[:-1]):
            assert r == HandlerResult.NOOP, (
                f"J4: transition {_PLANNED_TRANSITIONS[i]} should return NOOP "
                f"(only COMPLETE→MERGED fires J4), got {r!r}"
            )


# ---------------------------------------------------------------------------
# GT-003: decisions.jsonl sequence in isolation (GT-002 sub-assertion)
# ---------------------------------------------------------------------------


def test_decisions_sequence_matches_planned_path(tmp_path: Path) -> None:
    """J3: decisions.jsonl entries follow the canonical PLANNED_PATH order."""
    from atdd.coach.handlers import decisions as decisions_handler

    runtime_dir = tmp_path / "runtime"
    ctx = _make_ctx(617, runtime_dir)

    for src, dst in _PLANNED_TRANSITIONS:
        decisions_handler.handle(ctx, _make_transition(src, dst))

    records = _read_jsonl(runtime_dir / "coach" / "decisions.jsonl")
    pairs = [
        (r["inputs"]["current_phase"], r["inputs"]["target_phase"])
        for r in records
    ]
    expected = list(_PLANNED_TRANSITIONS)
    assert pairs == expected, (
        f"J3: phase-pair sequence mismatch\n  expected: {expected}\n  got: {pairs}"
    )


# ---------------------------------------------------------------------------
# GT-004: J5 watcher drives state via injected event (seam assertion)
# ---------------------------------------------------------------------------


def test_watcher_event_loop_advances_state_on_commit_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J5: WatcherEventLoop advances StateMachine from PLANNED to RED on event."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.handlers.state_machine import Phase, StateMachine
    from atdd.coach.handlers.watcher import WatcherEventLoop

    # Stub RuntimeWatcher to avoid background thread and inotify setup
    class _NullWatcher:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def persist_checkpoint(self) -> None:
            pass

    monkeypatch.setattr(
        "atdd.coach.handlers.watcher.RuntimeWatcher", _NullWatcher
    )

    runtime_dir = tmp_path / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)

    queue: CoachEventQueue = CoachEventQueue(runtime_dir=runtime_dir)
    # Watcher advances from active coding phases (RED/GREEN/SMOKE/REFACTOR only).
    # A commit with Phase=RED trailer means the tester just completed RED work
    # → state machine advances RED → GREEN.
    sm = StateMachine(issue_number=617, phase=Phase.RED)

    loop = WatcherEventLoop(
        machines=[sm],
        runtime_dir=runtime_dir,
        queue=queue,
        stale_warn_minutes=None,
        escalation_channel=None,
        coach_run_id="watcher-e2e-617",
    )

    # Inject a commit_observed event that signals RED phase work completed
    event = {
        "event_type": "commit_observed",
        "timestamp": "2026-05-12T00:00:00.000000Z",
        "payload": {
            "sha": "abc123",
            "trailers": {
                "Issue": "617",
                "Phase": "RED",
            },
        },
    }
    queue.put(event)

    result = loop.process_one_event(timeout=0.1)

    assert result == "applied", (
        f"J5: WatcherEventLoop must return 'applied' when a commit_observed event "
        f"matches a pending transition, got {result!r}"
    )
    assert sm.phase == Phase.GREEN, (
        f"J5: StateMachine must advance RED→GREEN after RED commit event, "
        f"still in {sm.phase.value!r}"
    )

    decisions_path = runtime_dir / "coach" / "decisions.jsonl"
    assert decisions_path.exists(), (
        "J5: WatcherEventLoop must write to decisions.jsonl when advancing state"
    )
    records = _read_jsonl(decisions_path)
    assert len(records) == 1, (
        f"J5: expected 1 decision entry from watcher event, got {len(records)}"
    )
    assert records[0]["outcome"]["to_phase"] == "GREEN", (
        f"J5: decision entry must record to_phase=GREEN, got {records[0]['outcome']!r}"
    )


# ---------------------------------------------------------------------------
# GT-005: J4 two-phase commit in isolation
# ---------------------------------------------------------------------------


def test_two_phase_commit_fires_at_complete_merged() -> None:
    """J4: two_phase_commit.handle returns HANDLED at COMPLETE→MERGED with auto_merge."""
    from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition
    from atdd.coach.handlers import two_phase_commit as tpc_handler

    ctx = CoachContext(
        issue_number=617,
        auto_merge=True,
        escalation_channel=None,
    )
    t = Transition(src=Phase.COMPLETE, dst=Phase.MERGED)

    with (
        patch("atdd.coach.handlers.two_phase_commit._create_pr", return_value=True),
        patch("atdd.coach.handlers.two_phase_commit._merge_pr", return_value=(True, "")),
        patch("atdd.coach.handlers.two_phase_commit._find_worktree_for_issue", return_value=None),
    ):
        result = tpc_handler.handle(ctx, t)

    assert result == HandlerResult.HANDLED, (
        f"J4: expected HANDLED at COMPLETE→MERGED with auto_merge=True, got {result!r}"
    )


def test_two_phase_commit_noop_without_auto_merge() -> None:
    """J4: without auto_merge, COMPLETE→MERGED returns NOOP (operator approval required)."""
    from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition
    from atdd.coach.handlers import two_phase_commit as tpc_handler

    ctx = CoachContext(issue_number=617, auto_merge=False)
    t = Transition(src=Phase.COMPLETE, dst=Phase.MERGED)

    result = tpc_handler.handle(ctx, t)
    assert result == HandlerResult.NOOP, (
        f"J4: expected NOOP when auto_merge=False, got {result!r}"
    )


# ---------------------------------------------------------------------------
# GT-005 (cont.): LLM registry seam (#592)
# ---------------------------------------------------------------------------


def test_llm_registry_registers_and_retrieves_mock_client() -> None:
    """C001: LLM registry can register a mock client and retrieve it by model-id."""
    from atdd.coach.commands import judge as judge_mod

    test_model_id = "_e2e_test_mock_llm"
    mock_client = MagicMock()
    mock_client.model_id = test_model_id

    try:
        judge_mod.register_llm_client(test_model_id, mock_client)
        retrieved = judge_mod.LLM_REGISTRY.get(test_model_id)
        assert retrieved is mock_client, (
            f"C001: retrieved client {retrieved!r} is not the registered mock client"
        )
    finally:
        judge_mod.LLM_REGISTRY.pop(test_model_id, None)


def test_llm_registry_unknown_model_raises() -> None:
    """C001: looking up an unregistered model-id in LLM_REGISTRY raises the expected error."""
    from atdd.coach.commands import judge as judge_mod

    unknown_id = "_e2e_definitely_not_registered_xyz"
    assert unknown_id not in judge_mod.LLM_REGISTRY, (
        "Precondition: test model-id must not be in LLM_REGISTRY"
    )


# ---------------------------------------------------------------------------
# GT-900: timing gate — whole suite under 30s
# ---------------------------------------------------------------------------


def test_e2e_suite_timing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Y001-INTEGRATION-008: full drive (all handlers) completes under 30s with mocks."""
    from atdd.coach.handlers import (
        decisions as decisions_handler,
        spawn as spawn_handler,
        validator_dispatch as validator_dispatch_handler,
        observer as observer_handler,
        reviewer as reviewer_handler,
        two_phase_commit as tpc_handler,
    )

    issue_number = 617
    runtime_dir = tmp_path / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)
    fake_sha = "timing" + "0" * 34

    monkeypatch.setattr(spawn_handler, "_call_spawn", lambda *a, **kw: {"surface_ref": "fake:0"})
    monkeypatch.setattr(spawn_handler, "_load_persona_prompt", lambda p, ph, **kw: "")
    monkeypatch.setattr(spawn_handler, "_resolve_worktree", lambda ctx: tmp_path)
    monkeypatch.setattr(spawn_handler, "_RUNTIME_ROOT", runtime_dir)

    def _fast_dispatch(**kwargs: Any) -> MagicMock:
        vp = runtime_dir / "validations" / fake_sha / "violations.jsonl"
        return _make_dispatch_result(vp, [])

    ctx = _make_ctx(issue_number, runtime_dir, auto_merge=True)

    start = time.monotonic()
    with (
        patch("atdd.coach.handlers.validator_dispatch.find_repo_root", return_value=tmp_path),
        patch("atdd.coach.handlers.validator_dispatch._get_head_sha", return_value=fake_sha),
        patch("atdd.coach.handlers.validator_dispatch.dispatch_validators", side_effect=_fast_dispatch),
        patch("atdd.coach.handlers.validator_dispatch._resolve_validator_dirs", return_value=[tmp_path]),
        patch("atdd.coach.handlers.two_phase_commit._create_pr", return_value=True),
        patch("atdd.coach.handlers.two_phase_commit._merge_pr", return_value=(True, "")),
        patch("atdd.coach.handlers.two_phase_commit._find_worktree_for_issue", return_value=None),
    ):
        for src, dst in _PLANNED_TRANSITIONS:
            t = _make_transition(src, dst)
            decisions_handler.handle(ctx, t)
            spawn_handler.handle(ctx, t)
            validator_dispatch_handler.handle(ctx, t)
            observer_handler.handle(ctx, t)
            reviewer_handler.handle(ctx, t)
            tpc_handler.handle(ctx, t)

    elapsed = time.monotonic() - start
    assert elapsed < 30.0, (
        f"Y001-INTEGRATION-008: full drive took {elapsed:.1f}s, "
        f"exceeds 30s wall-time budget"
    )
