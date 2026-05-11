# URN: test:integration-hardening:m3-validator-dispatch:M001-INTEGRATION-003-risk-threshold-block
# Acceptance: acc:integration-hardening:M001-INTEGRATION-003-risk-threshold-block
# WMBT: wmbt:integration-hardening:M001
# Phase: RED
# Layer: integration
"""M3-INTEGRATION-003 — --risk-threshold-block gates transitions.

Verifies that `ctx.risk_threshold_block` blocks any transition whose
post-validation `risk_score.sum > threshold` and allows transitions
when the sum is within the threshold.

Per spec §6.4 step 5 the threshold is compared against the sum field
of the written risk-score.json document after suppression filtering.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition


def _make_ctx(**kwargs) -> CoachContext:
    defaults = {"issue_number": 7, "dry_run": False}
    defaults.update(kwargs)
    return CoachContext(**defaults)


def _make_dispatch_result(violations_path: Path, violations: list[dict]) -> MagicMock:
    violations_path.parent.mkdir(parents=True, exist_ok=True)
    with violations_path.open("w") as fh:
        for v in violations:
            fh.write(json.dumps(v) + "\n")
    m = MagicMock()
    m.violations_path = violations_path
    m.exit_code = 0 if not violations else 1
    return m


def _run_handle(ctx, transition, tmp_path, violations: list[dict]):
    sha = "feedface" + "0" * 32
    runtime_dir = tmp_path / ".atdd" / "runtime"
    violations_path = runtime_dir / "validations" / sha / "violations.jsonl"
    dispatch_result = _make_dispatch_result(violations_path, violations)

    with (
        patch("atdd.coach.handlers.validator_dispatch.find_repo_root", return_value=tmp_path),
        patch("atdd.coach.handlers.validator_dispatch._get_head_sha", return_value=sha),
        patch("atdd.coach.handlers.validator_dispatch.dispatch_validators", return_value=dispatch_result),
        patch("atdd.coach.handlers.validator_dispatch._resolve_validator_dirs", return_value=[tmp_path / "v"]),
    ):
        from atdd.coach.handlers.validator_dispatch import handle
        result = handle(ctx, transition)

    risk_path = tmp_path / ".atdd" / "runtime" / "validations" / sha / "risk-score.json"
    return result, risk_path


def _advisory_violation(severity: int, idx: int) -> dict:
    return {
        "validator_id": f"test_adv::test_{idx}",
        "rule_id": f"coder.docs.missing-docstring",
        "severity": severity,
        "disposition": "advisory",
        "location": f"src/module_{idx}.py:1",
        "detail": f"advisory violation {idx}",
        "suppression_marker": None,
    }


def test_risk_exceeds_threshold_blocks(tmp_path):
    """sum=12 with threshold=10 blocks the transition."""
    # Three advisory severity-4 violations → sum = 12
    violations = [_advisory_violation(severity=4, idx=i) for i in range(3)]
    ctx = _make_ctx(risk_threshold_block=10)
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, risk_path = _run_handle(ctx, transition, tmp_path, violations)

    assert risk_path.exists()
    data = json.loads(risk_path.read_text())
    assert data["sum"] >= 12

    assert result == HandlerResult.BLOCKED


def test_risk_at_threshold_passes(tmp_path):
    """sum == threshold is NOT blocked (only strictly exceeding blocks)."""
    # Two advisory severity-5 violations → sum = 10
    violations = [_advisory_violation(severity=5, idx=i) for i in range(2)]
    ctx = _make_ctx(risk_threshold_block=10)
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, risk_path = _run_handle(ctx, transition, tmp_path, violations)

    data = json.loads(risk_path.read_text())
    assert data["sum"] == 10

    assert result == HandlerResult.HANDLED


def test_risk_below_threshold_passes(tmp_path):
    """sum < threshold allows the transition."""
    # One advisory severity-3 violation → sum = 3
    violations = [_advisory_violation(severity=3, idx=0)]
    ctx = _make_ctx(risk_threshold_block=10)
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, risk_path = _run_handle(ctx, transition, tmp_path, violations)

    data = json.loads(risk_path.read_text())
    assert data["sum"] == 3

    assert result == HandlerResult.HANDLED


def test_no_threshold_never_blocks_on_risk_alone(tmp_path):
    """Without --risk-threshold-block even a large risk sum allows the transition."""
    # Ten advisory severity-5 violations → sum = 50, but no threshold
    violations = [_advisory_violation(severity=5, idx=i) for i in range(10)]
    ctx = _make_ctx(risk_threshold_block=None)
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result, _ = _run_handle(ctx, transition, tmp_path, violations)

    assert result == HandlerResult.HANDLED


def test_risk_threshold_written_to_risk_score_json(tmp_path):
    """The risk-score.json document always exists after a dispatch regardless of threshold."""
    violations = [_advisory_violation(severity=2, idx=0)]
    ctx = _make_ctx(risk_threshold_block=5)
    transition = Transition(src=Phase.SMOKE, dst=Phase.REFACTOR)

    result, risk_path = _run_handle(ctx, transition, tmp_path, violations)

    assert risk_path.exists()
    data = json.loads(risk_path.read_text())
    assert "sum" in data
    assert "by_severity" in data
    assert data["phase"] == "SMOKE"
