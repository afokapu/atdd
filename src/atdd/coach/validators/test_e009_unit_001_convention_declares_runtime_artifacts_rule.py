# URN: test:govern-lifecycle:validator-blocks-runtime-artifacts-in-pr-diff:E009-UNIT-001-convention-declares-runtime-artifacts-rule
# Acceptance: acc:govern-lifecycle:E009-UNIT-001-convention-declares-runtime-artifacts-rule
# WMBT: wmbt:govern-lifecycle:E009
# Phase: RED
# Layer: backend.unit
# Assertion: structural

"""E009-UNIT-001 — pr.convention.yaml declares coach.pr.runtime-artifacts-blocked
with severity 4, disposition strict, and a fix_hint that names .atdd/runtime/.

Phase RED: fails because the rule has not been added to pr.convention.yaml yet.
Phase GREEN: rule exists; bind_rule() resolves and rules show exits 0.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]

REPO_ROOT = find_repo_root()
PR_CONVENTION = REPO_ROOT / "src" / "atdd" / "coach" / "conventions" / "pr.convention.yaml"

RULE_ID = "coach.pr.runtime-artifacts-blocked"


def test_convention_file_has_rule() -> None:
    """pr.convention.yaml must declare coach.pr.runtime-artifacts-blocked."""
    assert PR_CONVENTION.exists(), f"Missing {PR_CONVENTION}"
    text = PR_CONVENTION.read_text(encoding="utf-8")
    assert RULE_ID in text, (
        f"Rule '{RULE_ID}' not found in {PR_CONVENTION}. "
        "Add it under the rules: section with severity: 4, disposition: strict, "
        "and a fix_hint referencing .atdd/runtime/."
    )


def test_bind_rule_resolves() -> None:
    """bind_rule() must find coach.pr.runtime-artifacts-blocked without error."""
    rule = bind_rule(RULE_ID)
    assert rule.rule_id == RULE_ID, f"Expected rule_id {RULE_ID!r}, got {rule.rule_id!r}"
    assert rule.severity == 4, f"Expected severity 4, got {rule.severity}"


def test_disposition_is_strict() -> None:
    """Rule disposition must be strict (bypass forbidden)."""
    rule = bind_rule(RULE_ID)
    assert rule.disposition == "strict", (
        f"Expected disposition 'strict', got {rule.disposition!r}. "
        "Runtime artifacts in PRs is never intentional; bypass must be forbidden."
    )


def test_fix_hint_names_runtime_path() -> None:
    """Rule fix_hint must reference .atdd/runtime/ so agents know the remedy."""
    rule = bind_rule(RULE_ID)
    hint = (rule.fix_hint or "").lower()
    assert ".atdd/runtime" in hint, (
        f"Rule fix_hint does not mention .atdd/runtime/. Got: {rule.fix_hint!r}. "
        "The fix_hint must name the offending pattern so agents can diagnose violations."
    )


def test_rules_show_exits_zero() -> None:
    """atdd rules show coach.pr.runtime-artifacts-blocked must exit 0."""
    import os

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    result = subprocess.run(
        ["atdd", "rules", "show", RULE_ID],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert result.returncode == 0, (
        f"atdd rules show {RULE_ID} exited {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert RULE_ID in result.stdout, (
        f"Expected rule_id in output, got:\n{result.stdout}"
    )
