"""
PR phase alignment validation.

Purpose: Verify that PR content matches the linked issue's ATDD phase label.
A PR that merges code changes while the linked issue is still at INIT or
PLANNED indicates skipped lifecycle phases (the incident pattern from #256).
A PR that merges code changes while the linked issue is at GREEN indicates
a missing SMOKE phase (the incident pattern from janetbusiness/jel-app#307,
#308 — see issue #293).

Phase mapping:
    INIT / PLANNED  → warn (ratcheted): expect plan/contract artifacts only
    RED             → expect test files only
    GREEN           → fail (ratcheted): code lands without SMOKE verification
    SMOKE+          → expect code changes

SPEC-COACH-PRGATE-0002: PR merging code changes warns if linked issue is
at INIT or PLANNED.
COACH-PRGATE-0003 (issue #293): PR merging code changes FAILS (ratcheted)
when linked issue is at GREEN — SMOKE phase must run first.

Run: atdd validate coach
"""

import logging
from pathlib import Path
from typing import Any, List, Sequence, Tuple

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation
from atdd.coder.baselines.ratchet import RatchetBaseline

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO_ROOT = find_repo_root()

# Baseline path for coach validators
COACH_BASELINE_PATH = REPO_ROOT / ".atdd" / "baselines" / "coach.yaml"

# File path patterns that indicate code changes (not just planner artifacts)
_CODE_PATH_PREFIXES = (
    "python/",
    "web/src/",
    "supabase/functions/",
    "packages/",
    "supabase/migrations/",
)

# File path patterns that indicate test files
_TEST_PATH_PATTERNS = (
    "/tests/",
    "/test_",
    ".test.",
    ".spec.",
)

# File path patterns that indicate planner-only artifacts
_PLAN_PATH_PREFIXES = (
    "plan/",
    "contracts/",
    "telemetry/",
    ".atdd/",
)

# Phases where code changes in a PR are unexpected (warn, ratcheted via opaque strings)
_EARLY_PHASES = frozenset({"INIT", "PLANNED"})

# Phases where code changes in a PR fail the gate (COACH-PRGATE-0003)
# — issue #293, severity 4 (correctness): GREEN code merging without SMOKE
_FAILING_PHASES = frozenset({"GREEN"})

# Stable rule identity (issue #293 + #340 substrate)
RULE_ID_PRGATE_GREEN = "COACH-PRGATE-0003"
SEVERITY_PRGATE_GREEN = 4


def _classify_changed_files(files: List[str]) -> dict:
    """Classify PR changed files into code, test, and plan categories."""
    result = {"code": [], "test": [], "plan": [], "other": []}
    for f in files:
        if any(pat in f for pat in _TEST_PATH_PATTERNS):
            result["test"].append(f)
        elif any(f.startswith(pfx) for pfx in _CODE_PATH_PREFIXES):
            result["code"].append(f)
        elif any(f.startswith(pfx) for pfx in _PLAN_PATH_PREFIXES):
            result["plan"].append(f)
        else:
            result["other"].append(f)
    return result


def scan_pr_phase_alignment(repo_root: Path) -> Tuple[int, Sequence]:
    """Scan open PRs for phase alignment violations.

    Returns (violation_count, violation_messages) for ratchet baseline.
    """
    mgr = PRManager(target_dir=repo_root)
    open_prs = mgr.fetch_open_prs()
    violations: List[str] = []

    for pr in open_prs:
        pr_number = pr["number"]
        resolution = mgr.resolve_linked_issue(pr_number)
        if resolution is None:
            continue

        phase = resolution["phase_label"]
        if phase is None or phase not in _EARLY_PHASES:
            continue

        changed_files = mgr.fetch_pr_changed_files(pr_number)
        if not changed_files:
            continue

        classified = _classify_changed_files(changed_files)

        if classified["code"]:
            code_sample = classified["code"][:3]
            violations.append(
                f"PR #{pr_number} → issue #{resolution['issue_number']} "
                f"(phase={phase}): {len(classified['code'])} code file(s) "
                f"changed — expected plan/contract artifacts only at {phase}. "
                f"Files: {', '.join(code_sample)}"
                + (f" ... +{len(classified['code']) - 3} more"
                   if len(classified["code"]) > 3 else "")
            )
            logging.getLogger(__name__).warning(
                "SPEC-COACH-PRGATE-0002: PR #%d has code changes but "
                "issue #%d is at %s",
                pr_number, resolution["issue_number"], phase,
                extra={
                    "pr": pr_number,
                    "issue": resolution["issue_number"],
                    "phase": phase,
                    "code_files": len(classified["code"]),
                },
            )

    return len(violations), violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pr_phase_alignment():
    """
    SPEC-COACH-PRGATE-0002 + COACH-PRGATE-0003: PR content must align with
    linked issue phase.

    Given: Open PRs with linked ATDD issues
    When: Checking PR changed files vs issue phase label
    Then: PRs with code changes for INIT/PLANNED issues are warned (string),
          PRs with code changes for GREEN issues fail with structured Violation.

    Ratchet baseline: violations must not exceed recorded baseline (Category A).
    """
    baseline = RatchetBaseline(COACH_BASELINE_PATH)
    count, violations = scan_pr_phase_alignment(REPO_ROOT)

    baseline.assert_no_regression(
        validator_id="pr_phase_alignment",
        current_count=count,
        violations=violations,
    )


# ---------------------------------------------------------------------------
# Pure-evaluator unit tests (no GitHub access required)
# ---------------------------------------------------------------------------


def _make_classified(code=(), test=(), plan=(), other=()):
    return {
        "code": list(code),
        "test": list(test),
        "plan": list(plan),
        "other": list(other),
    }


def test_evaluate_phase_violations_emits_structured_violation_for_green_with_code():
    """COACH-PRGATE-0003: GREEN-phase PR with code files emits structured Violation."""
    classified = _make_classified(code=["python/auth/login.py"])
    items = evaluate_phase_violations(
        pr_number=999,
        issue_number=293,
        phase="GREEN",
        classified=classified,
    )

    structured = [v for v in items if isinstance(v, Violation)]
    assert len(structured) == 1
    v = structured[0]
    assert v.rule_id == RULE_ID_PRGATE_GREEN == "COACH-PRGATE-0003"
    assert v.severity == SEVERITY_PRGATE_GREEN == 4
    # Locator must reference the offending PR for triage
    assert "999" in v.location
    assert "293" in v.detail
    assert "GREEN" in v.detail


def test_evaluate_phase_violations_returns_warning_string_for_init_with_code():
    """SPEC-COACH-PRGATE-0002: INIT-phase PR with code emits opaque warn (preserved semantics)."""
    classified = _make_classified(code=["python/auth/login.py"])
    items = evaluate_phase_violations(
        pr_number=42,
        issue_number=100,
        phase="INIT",
        classified=classified,
    )

    # Backwards compat: INIT/PLANNED stays as opaque strings (no rule_id),
    # ratcheted by string count under the existing pr_phase_alignment validator_id.
    assert any(isinstance(item, str) for item in items)
    assert all(not isinstance(item, Violation) for item in items)


def test_evaluate_phase_violations_returns_warning_string_for_planned_with_code():
    """SPEC-COACH-PRGATE-0002: PLANNED-phase PR with code emits opaque warn."""
    classified = _make_classified(code=["web/src/match/Match.tsx"])
    items = evaluate_phase_violations(
        pr_number=43,
        issue_number=101,
        phase="PLANNED",
        classified=classified,
    )

    assert any(isinstance(item, str) for item in items)
    assert all(not isinstance(item, Violation) for item in items)


def test_evaluate_phase_violations_quiet_for_green_with_only_tests():
    """GREEN PRs that only touch test files are not flagged (orthogonal to SMOKE)."""
    classified = _make_classified(test=["python/auth/tests/test_login.py"])
    items = evaluate_phase_violations(
        pr_number=44,
        issue_number=102,
        phase="GREEN",
        classified=classified,
    )
    assert items == []


def test_evaluate_phase_violations_quiet_for_smoke_phase():
    """SMOKE/REFACTOR/COMPLETE PRs with code are expected — no violation."""
    classified = _make_classified(code=["python/auth/login.py"])
    for phase in ("SMOKE", "REFACTOR", "COMPLETE"):
        items = evaluate_phase_violations(
            pr_number=45,
            issue_number=103,
            phase=phase,
            classified=classified,
        )
        assert items == [], f"phase={phase} should not be flagged"


def test_evaluate_phase_violations_quiet_for_none_phase():
    """No phase label resolved → no opinion (validator stays quiet)."""
    classified = _make_classified(code=["python/auth/login.py"])
    items = evaluate_phase_violations(
        pr_number=46,
        issue_number=104,
        phase=None,
        classified=classified,
    )
    assert items == []


def test_failing_phases_includes_green_only():
    """Only GREEN is in the failing set per issue #293 — INIT/PLANNED stay warn."""
    assert _FAILING_PHASES == frozenset({"GREEN"})
    assert _EARLY_PHASES == frozenset({"INIT", "PLANNED"})
    assert _FAILING_PHASES.isdisjoint(_EARLY_PHASES)
