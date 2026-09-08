# URN: test:govern-lifecycle:bind-issue-feature:C011-SMOKE-001-real-validate-coach-reports-the-binding
# Acceptance: acc:govern-lifecycle:C011-SMOKE-001-real-validate-coach-reports-the-binding
# WMBT: wmbt:govern-lifecycle:C011
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The real `atdd validate coach --local` selects and runs this validator, so the rule is enforced by the shipped gate rather than only by a test that imports it.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:C011-SMOKE-001-real-validate-coach-reports-the-binding
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:C011

Purpose: a validator the shipped gate never selects enforces nothing.

This is not hypothetical in this repo. `atdd validate planner --local
--skip-api` selects -m "(not github_api) and (not platform)" and thereby
deselects roughly 207 platform-marked validators; during this issue's planner
pass the mandated gate was GREEN at 211 passed while the full validator
directory was RED. Selection is therefore asserted, never assumed.

Real: the validator file is discovered the way CI discovers it — by collecting
the real validator directory in a real pytest subprocess.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_SRC = Path(__file__).resolve().parents[4]
_COACH_VALIDATORS = _SRC / "atdd" / "coach" / "validators"

# The validator file the shipped gate must collect and run.
_VALIDATOR_FILE = _COACH_VALIDATORS / "test_issue_feature_binding.py"
_RULE_ID = "coach.issue.feature-binding-must-resolve"


def _collect(*extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(_COACH_VALIDATORS),
         "--collect-only", "-q", *extra],
        cwd=_SRC.parent, env=env, capture_output=True, text=True, timeout=300,
    )


def test_the_validator_file_ships_in_the_coach_validator_directory() -> None:
    """CI runs `pytest src/atdd/coach/validators/`; the rule must live there."""
    assert _VALIDATOR_FILE.exists(), (
        f"expected the feature-binding validator at {_VALIDATOR_FILE}. A rule "
        "whose validator lives outside the five CI-collected paths is not "
        "enforced by CI at all (#1643)."
    )


def test_the_real_gate_collects_the_validator() -> None:
    """Discovered and selected the way CI discovers it — not merely importable."""
    result = _collect()
    assert result.returncode == 0, (
        f"collecting the coach validator directory failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "test_issue_feature_binding" in result.stdout, (
        "the feature-binding validator was not collected by the real gate, so "
        "it enforces nothing regardless of what it asserts"
    )


def test_the_validator_survives_the_gate_marker_expression() -> None:
    """The trap that hid a real failure during this issue's planner pass.

    `atdd validate <phase> --local --skip-api` deselects `platform`-marked
    tests. A validator that only runs when the marker filter is absent is
    invisible to the mandated gate.
    """
    result = _collect("-m", "(not github_api) and (not platform)")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "test_issue_feature_binding" in result.stdout, (
        "the feature-binding validator is deselected by the gate's own marker "
        "expression, so `atdd validate coach --local --skip-api` would report "
        "PASS while never running it"
    )


def test_the_rule_resolves_through_the_shipped_registry() -> None:
    """The rule must be registered, not just referenced by a test."""
    from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

    try:
        bind_rule(_RULE_ID)
    except RuleNotInRegistryError as exc:
        pytest.fail(f"rule {_RULE_ID!r} is not in the shipped registry: {exc}")
