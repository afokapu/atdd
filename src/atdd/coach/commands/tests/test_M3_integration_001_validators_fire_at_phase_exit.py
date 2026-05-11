# URN: test:integration-hardening:m3-validator-dispatch:M001-INTEGRATION-001-validators-fire-at-phase-exit
# Acceptance: acc:integration-hardening:M001-INTEGRATION-001-validators-fire-at-phase-exit
# WMBT: wmbt:integration-hardening:M001
# Phase: RED
# Layer: integration
"""M3-INTEGRATION-001 — validators fire at phase exit and produce artifacts.

Verifies that `atdd.coach.handlers.validator_dispatch.handle()` invokes the
M3 dispatcher at each phase-exit gate and produces:
  - `.atdd/runtime/coach/validations/<sha>/violations.jsonl`
  - `.atdd/runtime/coach/validations/<sha>/suppressed.jsonl` (when applicable)
  - `.atdd/runtime/coach/validations/<sha>/risk-score.json`

Per spec §6.4 step 5 the phase-appropriate validator subset runs:
  - planner-validators at INIT exit (INIT→PLANNED)
  - coder-validators at GREEN exit (GREEN→SMOKE)

The dispatcher itself is mocked — this test verifies the wiring, not the
subprocess.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.handlers.state_machine import CoachContext, Phase, Transition


def _make_ctx(**kwargs) -> CoachContext:
    defaults = {"issue_number": 42, "dry_run": False}
    defaults.update(kwargs)
    return CoachContext(**defaults)


def _make_dispatch_result(violations_path: Path, violations: list[dict]) -> MagicMock:
    """Build a fake DispatchResult whose violations_path holds the given records."""
    violations_path.parent.mkdir(parents=True, exist_ok=True)
    with violations_path.open("w") as fh:
        for v in violations:
            fh.write(json.dumps(v) + "\n")
    result = MagicMock()
    result.violations_path = violations_path
    result.exit_code = 0
    return result


def _run_handle(ctx, transition, tmp_path, violations: list[dict]):
    sha = "deadbeef" + "0" * 32

    runtime_dir = tmp_path / ".atdd" / "runtime"
    violations_path = runtime_dir / "validations" / sha / "violations.jsonl"

    dispatch_result = _make_dispatch_result(violations_path, violations)

    with (
        patch("atdd.coach.handlers.validator_dispatch.find_repo_root", return_value=tmp_path),
        patch("atdd.coach.handlers.validator_dispatch._get_head_sha", return_value=sha),
        patch("atdd.coach.handlers.validator_dispatch.dispatch_validators", return_value=dispatch_result) as mock_dispatch,
        patch("atdd.coach.handlers.validator_dispatch._resolve_validator_dirs", return_value=[tmp_path / "validators"]),
    ):
        from atdd.coach.handlers.validator_dispatch import handle

        result = handle(ctx, transition)

    return result, sha, tmp_path, mock_dispatch


def test_green_exit_dispatcher_is_called(tmp_path):
    """At GREEN→SMOKE the dispatcher is invoked with validator paths."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, sha, root, mock_dispatch = _run_handle(ctx, transition, tmp_path, [])

    mock_dispatch.assert_called_once()
    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["sha"] == sha
    assert call_kwargs["repo_root"] == root


def test_green_exit_produces_risk_score_artifact(tmp_path):
    """After GREEN exit, risk-score.json exists under the SHA runtime dir."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, sha, root, _ = _run_handle(ctx, transition, tmp_path, [])

    risk_path = root / ".atdd" / "runtime" / "validations" / sha / "risk-score.json"
    assert risk_path.exists(), f"risk-score.json not found at {risk_path}"
    data = json.loads(risk_path.read_text())
    assert "sum" in data
    assert data["phase"] == "GREEN"
    assert data["sha"] == sha


def test_init_exit_dispatcher_is_called(tmp_path):
    """At INIT→PLANNED the dispatcher fires (planner validator subset)."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)

    result, sha, root, mock_dispatch = _run_handle(ctx, transition, tmp_path, [])

    mock_dispatch.assert_called_once()


def test_dry_run_skips_dispatch(tmp_path):
    """When ctx.dry_run=True the dispatcher is not called but HANDLED is returned."""
    from atdd.coach.handlers.state_machine import HandlerResult

    ctx = _make_ctx(dry_run=True)
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    with (
        patch("atdd.coach.handlers.validator_dispatch.find_repo_root", return_value=tmp_path),
        patch("atdd.coach.handlers.validator_dispatch._get_head_sha", return_value="drysha"),
        patch("atdd.coach.handlers.validator_dispatch._resolve_validator_dirs", return_value=[tmp_path]),
    ):
        with patch("atdd.coach.handlers.validator_dispatch.dispatch_validators") as mock_dispatch:
            from atdd.coach.handlers.validator_dispatch import handle
            result = handle(ctx, transition)

    mock_dispatch.assert_not_called()
    assert result == HandlerResult.HANDLED


def test_noop_on_non_forward_transition(tmp_path):
    """BLOCKED→RED is not a forward exit — handler returns NOOP."""
    from atdd.coach.handlers.state_machine import HandlerResult

    ctx = _make_ctx()
    transition = Transition(src=Phase.BLOCKED, dst=Phase.RED)

    with patch("atdd.coach.handlers.validator_dispatch.dispatch_validators") as mock_dispatch:
        from atdd.coach.handlers.validator_dispatch import handle
        result = handle(ctx, transition)

    mock_dispatch.assert_not_called()
    assert result == HandlerResult.NOOP


def test_no_violations_returns_handled(tmp_path):
    """An empty violations.jsonl (all clear) → HANDLED, not BLOCKED."""
    from atdd.coach.handlers.state_machine import HandlerResult

    ctx = _make_ctx()
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, sha, root, _ = _run_handle(ctx, transition, tmp_path, violations=[])

    assert result == HandlerResult.HANDLED


def test_phase_field_in_risk_score_matches_exited_phase(tmp_path):
    """risk-score.json `phase` field records which phase was exited."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.SMOKE, dst=Phase.REFACTOR)

    result, sha, root, _ = _run_handle(ctx, transition, tmp_path, [])

    risk_path = root / ".atdd" / "runtime" / "validations" / sha / "risk-score.json"
    data = json.loads(risk_path.read_text())
    assert data["phase"] == "SMOKE"
