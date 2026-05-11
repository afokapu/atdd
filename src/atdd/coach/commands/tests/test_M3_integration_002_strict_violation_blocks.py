# URN: test:integration-hardening:m3-validator-dispatch:M3-INTEGRATION-002-strict-violation-blocks
# Acceptance: acc:integration-hardening:M3-INTEGRATION-002-strict-violation-blocks
# WMBT: wmbt:integration-hardening:M3
# Phase: RED
# Layer: integration
"""M3-INTEGRATION-002 — strict-disposition violation blocks RED→GREEN.

Verifies that when the dispatcher produces a `strict`-disposition violation
the handler returns BLOCKED, preventing the transition from advancing.

Per spec §6.4 step 5 only `strict` violations block. `advisory` and
`suppress-and-clean` (when absorbed by a valid marker) do not.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition


def _make_ctx(**kwargs) -> CoachContext:
    defaults = {"issue_number": 99, "dry_run": False}
    defaults.update(kwargs)
    return CoachContext(**defaults)


def _make_dispatch_result(violations_path: Path, violations: list[dict]) -> MagicMock:
    violations_path.parent.mkdir(parents=True, exist_ok=True)
    with violations_path.open("w") as fh:
        for v in violations:
            fh.write(json.dumps(v) + "\n")
    m = MagicMock()
    m.violations_path = violations_path
    m.exit_code = 1
    return m


def _run_handle(ctx, transition, tmp_path, violations: list[dict]):
    sha = "cafebabe" + "0" * 32
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

    return result


def test_strict_violation_blocks_red_to_green(tmp_path):
    """A strict violation in coder phase blocks RED→GREEN."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.RED, dst=Phase.GREEN)

    violations = [
        {
            "validator_id": "test_strict::test_fail",
            "rule_id": "coder.dead-code.reachability",
            "severity": 4,
            "disposition": "strict",
            "location": "src/module.py:10",
            "detail": "unreachable code block",
            "suppression_marker": None,
        }
    ]

    result = _run_handle(ctx, transition, tmp_path, violations)

    assert result == HandlerResult.BLOCKED


def test_advisory_violation_does_not_block(tmp_path):
    """An advisory violation must NOT block the transition."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.RED, dst=Phase.GREEN)

    violations = [
        {
            "validator_id": "test_adv::test_warn",
            "rule_id": "coder.docs.missing-docstring",
            "severity": 1,
            "disposition": "advisory",
            "location": "src/module.py:5",
            "detail": "missing docstring",
            "suppression_marker": None,
        }
    ]

    result = _run_handle(ctx, transition, tmp_path, violations)

    assert result == HandlerResult.HANDLED


def test_multiple_violations_one_strict_blocks(tmp_path):
    """Advisory + strict combination: handler returns BLOCKED."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    violations = [
        {
            "validator_id": "test_multi::test_advisory",
            "rule_id": "coder.docs.missing-docstring",
            "severity": 1,
            "disposition": "advisory",
            "location": "src/a.py:1",
            "detail": "missing docstring",
            "suppression_marker": None,
        },
        {
            "validator_id": "test_multi::test_strict",
            "rule_id": "coder.dead-code.reachability",
            "severity": 4,
            "disposition": "strict",
            "location": "src/b.py:20",
            "detail": "dead code",
            "suppression_marker": None,
        },
    ]

    result = _run_handle(ctx, transition, tmp_path, violations)

    assert result == HandlerResult.BLOCKED


def test_no_violations_returns_handled(tmp_path):
    """No violations means no block — HANDLED."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)

    result = _run_handle(ctx, transition, tmp_path, violations=[])

    assert result == HandlerResult.HANDLED


def test_strict_violation_recorded_in_risk_score(tmp_path):
    """Strict violation is counted in risk-score.json by_disposition."""
    ctx = _make_ctx()
    transition = Transition(src=Phase.GREEN, dst=Phase.SMOKE)
    sha = "deadc0de" + "0" * 32

    violations = [
        {
            "validator_id": "test_strict2::test_fail",
            "rule_id": "coder.dead-code.reachability",
            "severity": 4,
            "disposition": "strict",
            "location": "src/c.py:30",
            "detail": "dead code",
            "suppression_marker": None,
        }
    ]

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
        handle(ctx, transition)

    risk_path = tmp_path / ".atdd" / "runtime" / "validations" / sha / "risk-score.json"
    assert risk_path.exists()
    data = json.loads(risk_path.read_text())
    assert data["sum"] > 0
    assert data["by_disposition"].get("strict", 0) > 0
