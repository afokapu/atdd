"""
COACH-RATCHET-PRES-001: Presentation-layer ratchet improvements require SMOKE.

Detects when a single PR reduces a presentation-layer file's line count by
>20% relative to the merge base. When detected and no smoke evidence is
recorded for the issue, emits a structured Violation that blocks the
SMOKE→REFACTOR transition.

Conventions:
- src/atdd/coder/conventions/refactor.convention.yaml (rule declared)
- src/atdd/coder/conventions/presentation.convention.yaml (layer location)

Issue: #358 (replaces idea-issue #319 — past incident: 8 match features
silently removed during ratchet trimming).

Structured violations (issue #340): emits ``Violation(
    rule_id="COACH-RATCHET-PRES-001", severity=3, ...)`` records via
``assert_disposition_satisfied(...)``.

Severity rationale (per issue body, decision #5): 3 = advisory + gate, not
stop-the-world. Past incident took hours to find, not weeks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation


_RULE = bind_rule("coder.refactor.coach-ratchet-pres")
from atdd.coder.validators.presentation_ratchet import (
    PRESENTATION_GLOBS,
    PresentationReduction,
    PresentationRatchetRule,
    collect_repo_reductions,
    detect_presentation_reductions,
    has_smoke_evidence,
    record_smoke_evidence,
    smoke_evidence_dir,
    smoke_evidence_path,
)


# ---------------------------------------------------------------------------
# Pure detector: reductions
# ---------------------------------------------------------------------------

def test_detects_25pct_reduction_in_presentation_tsx():
    """200 → 150 lines = 25% reduction in a */presentation/*.tsx file → flagged."""
    diffs = [
        ("web/src/match/presentation/MatchPage.tsx", 200, 150),
    ]
    reductions = detect_presentation_reductions(diffs)
    assert len(reductions) == 1
    r = reductions[0]
    assert isinstance(r, PresentationReduction)
    assert r.path == "web/src/match/presentation/MatchPage.tsx"
    assert r.before_lines == 200
    assert r.after_lines == 150
    assert r.reduction_ratio == pytest.approx(0.25)


def test_full_deletion_treated_as_100pct_reduction():
    """Per decision #4 in issue body: deletions are even more dangerous than trims."""
    diffs = [
        ("python/auth/presentation/login_handler.py", 80, 0),
    ]
    reductions = detect_presentation_reductions(diffs)
    assert len(reductions) == 1
    assert reductions[0].reduction_ratio == pytest.approx(1.0)


def test_ignores_reductions_at_or_below_threshold():
    """20% threshold is exclusive — a 20% drop is allowed without smoke."""
    diffs = [
        ("web/src/match/presentation/Page.tsx", 100, 80),  # exactly 20%
        ("web/src/match/presentation/Other.tsx", 100, 90),  # 10%
    ]
    reductions = detect_presentation_reductions(diffs, threshold=0.20)
    assert reductions == []


def test_ignores_files_outside_presentation_layer():
    """Domain/application/integration files are out of scope for this rule."""
    diffs = [
        ("python/auth/domain/user.py", 200, 100),
        ("python/auth/application/use_cases/login.py", 200, 100),
        ("python/auth/integration/postgres_repo.py", 200, 100),
        ("web/src/match/components/Button.tsx", 200, 100),
    ]
    assert detect_presentation_reductions(diffs) == []


def test_ignores_growth_and_unchanged_files():
    """Only reductions matter; additions and equal-size diffs are ignored."""
    diffs = [
        ("web/src/match/presentation/Grew.tsx", 100, 200),  # grew
        ("web/src/match/presentation/Same.tsx", 100, 100),  # unchanged
    ]
    assert detect_presentation_reductions(diffs) == []


def test_ignores_zero_before_lines():
    """A new file (before=0) is an addition, not a reduction."""
    diffs = [
        ("web/src/match/presentation/New.tsx", 0, 50),
    ]
    assert detect_presentation_reductions(diffs) == []


def test_python_supabase_presentation_files_in_scope():
    """Per presentation.convention.yaml, presentation exists in py/ts/tsx."""
    diffs = [
        ("python/auth/presentation/handler.py", 100, 70),  # 30% drop
        ("supabase/functions/auth/presentation/route.ts", 100, 70),  # 30% drop
    ]
    reductions = detect_presentation_reductions(diffs)
    assert len(reductions) == 2


def test_default_globs_match_documented_extensions():
    """Per issue body Phase 1: walk */presentation/*.{tsx,ts,py} files."""
    assert "*/presentation/*.tsx" in PRESENTATION_GLOBS
    assert "*/presentation/*.ts" in PRESENTATION_GLOBS
    assert "*/presentation/*.py" in PRESENTATION_GLOBS


# ---------------------------------------------------------------------------
# Smoke evidence
# ---------------------------------------------------------------------------

def test_smoke_evidence_path_uses_dotatdd_directory(tmp_path):
    """Per issue body: .atdd/smoke-evidence/<issue>.yaml (gitignored)."""
    p = smoke_evidence_path(tmp_path, 358)
    assert p == tmp_path / ".atdd" / "smoke-evidence" / "358.yaml"


def test_smoke_evidence_dir_under_dotatdd(tmp_path):
    assert smoke_evidence_dir(tmp_path) == tmp_path / ".atdd" / "smoke-evidence"


def test_has_smoke_evidence_false_when_missing(tmp_path):
    assert has_smoke_evidence(tmp_path, 358) is False


def test_has_smoke_evidence_true_when_recorded(tmp_path):
    record_smoke_evidence(tmp_path, 358, recorded_by="alec", note="manual run")
    assert has_smoke_evidence(tmp_path, 358) is True


def test_record_smoke_evidence_persists_metadata(tmp_path):
    record_smoke_evidence(tmp_path, 358, recorded_by="alec", note="manual run")
    payload = yaml.safe_load(smoke_evidence_path(tmp_path, 358).read_text())
    assert payload["issue"] == 358
    assert payload["recorded_by"] == "alec"
    assert payload["note"] == "manual run"
    assert "recorded_at" in payload


# ---------------------------------------------------------------------------
# Rule emission
# ---------------------------------------------------------------------------

def test_rule_id_and_severity_are_documented_constants():
    assert PresentationRatchetRule.RULE_ID == "COACH-RATCHET-PRES-001"
    assert PresentationRatchetRule.SEVERITY == 3


def test_violation_emitted_when_evidence_missing():
    reduction = PresentationReduction(
        path="web/src/match/presentation/MatchPage.tsx",
        before_lines=200,
        after_lines=150,
        reduction_ratio=0.25,
    )
    violations = PresentationRatchetRule.violations_for(
        [reduction],
        has_evidence=False,
    )
    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, Violation)
    assert v.rule_id == "COACH-RATCHET-PRES-001"
    assert v.severity == 3
    assert "MatchPage.tsx" in v.location
    assert "25" in v.detail or "0.25" in v.detail


def test_no_violation_when_evidence_present():
    reduction = PresentationReduction(
        path="web/src/match/presentation/MatchPage.tsx",
        before_lines=200,
        after_lines=150,
        reduction_ratio=0.25,
    )
    violations = PresentationRatchetRule.violations_for(
        [reduction],
        has_evidence=True,
    )
    assert violations == []


def test_no_violation_when_no_reductions():
    violations = PresentationRatchetRule.violations_for([], has_evidence=False)
    assert violations == []


# ---------------------------------------------------------------------------
# Repo-driven collection (integration with git)
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(repo), text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "checkout", "-b", "main")
    return repo


def test_collect_repo_reductions_detects_presentation_trim(tmp_path):
    repo = _make_repo(tmp_path)
    pres = repo / "web/src/match/presentation/MatchPage.tsx"
    pres.parent.mkdir(parents=True)
    pres.write_text("\n".join(f"line{i}" for i in range(200)) + "\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed")

    _git(repo, "checkout", "-b", "feat/trim")
    pres.write_text("\n".join(f"line{i}" for i in range(150)) + "\n")
    _git(repo, "commit", "-q", "-am", "trim")

    reductions = collect_repo_reductions(repo, base_ref="main", head_ref="HEAD")
    assert len(reductions) == 1
    r = reductions[0]
    assert r.path.endswith("MatchPage.tsx")
    assert r.reduction_ratio == pytest.approx(0.25)


def test_collect_repo_reductions_handles_full_deletion(tmp_path):
    repo = _make_repo(tmp_path)
    pres = repo / "python/auth/presentation/handler.py"
    pres.parent.mkdir(parents=True)
    pres.write_text("\n".join(f"line{i}" for i in range(80)) + "\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed")

    _git(repo, "checkout", "-b", "feat/delete")
    pres.unlink()
    _git(repo, "commit", "-q", "-am", "delete")

    reductions = collect_repo_reductions(repo, base_ref="main", head_ref="HEAD")
    assert len(reductions) == 1
    assert reductions[0].reduction_ratio == pytest.approx(1.0)


def test_collect_repo_reductions_ignores_non_presentation(tmp_path):
    repo = _make_repo(tmp_path)
    domain = repo / "python/auth/domain/user.py"
    domain.parent.mkdir(parents=True)
    domain.write_text("\n".join(f"line{i}" for i in range(200)) + "\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed")

    _git(repo, "checkout", "-b", "feat/trim-domain")
    domain.write_text("\n".join(f"line{i}" for i in range(50)) + "\n")
    _git(repo, "commit", "-q", "-am", "trim")

    reductions = collect_repo_reductions(repo, base_ref="main", head_ref="HEAD")
    assert reductions == []


# ---------------------------------------------------------------------------
# End-to-end ratchet integration
# ---------------------------------------------------------------------------

@pytest.mark.coder
def test_presentation_ratchet_requires_smoke():
    """
    COACH-RATCHET-PRES-001: Presentation-layer reductions >20% require smoke.

    Given: A PR that reduces a */presentation/*.{tsx,ts,py} file by >20%
    When:  No smoke evidence has been recorded for the issue
    Then:  Validator emits a Violation that blocks SMOKE→REFACTOR

    On the toolkit-self repo (this validator's home) we expect zero
    presentation-layer reductions in this branch's diff against main —
    i.e. a clean run. Regression behavior is exercised by the unit tests
    above using synthetic diffs and a temp repo.
    """
    from atdd.coach.utils.repo import find_repo_root
    repo_root = find_repo_root()

    try:
        reductions = collect_repo_reductions(
            repo_root,
            base_ref="origin/main",
            head_ref="HEAD",
        )
    except subprocess.CalledProcessError:
        pytest.skip("git diff against origin/main unavailable")

    issue_number = _detect_issue_number(repo_root)
    has_evidence = (
        has_smoke_evidence(repo_root, issue_number)
        if issue_number is not None
        else False
    )

    violations: List[Violation] = PresentationRatchetRule.violations_for(
        reductions,
        has_evidence=has_evidence,
    )

    assert_disposition_satisfied(
        validator_id="presentation_ratchet_requires_smoke",
        violations=violations,
    )


def _detect_issue_number(repo_root: Path) -> int | None:
    """Best-effort: parse `<N>` from branch name or current worktree metadata."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None
    # Manifest-driven lookup happens elsewhere; this helper is intentionally
    # narrow to keep the validator runnable outside the CLI context.
    import re
    match = re.search(r"(\d+)", branch)
    return int(match.group(1)) if match else None
