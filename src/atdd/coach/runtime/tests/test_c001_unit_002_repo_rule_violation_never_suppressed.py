# URN: test:dispatch-validators:repo-rule-violation-never-suppressed
# Acceptance: acc:dispatch-validators:C001-UNIT-002-repo-rule-violation-never-suppressed
# WMBT: wmbt:dispatch-validators:C001
# Phase: GREEN
# Layer: domain

"""AC-UNIT-002: repo-rule violation never suppressed even with marker.

A repo-rule violation (substrate v12; walker-set ``disposition: strict``)
remains in the active set even when a ``# atdd:suppress(<repo-rule-id>)
[UNTIL=...]`` marker exists on the offending line; ``suppressed.jsonl``
contains zero records whose ``rule_id`` resolves to a ``repo.*`` rule,
even when markers are present.

This emerges from the existing ``disposition_gate`` strict-unconditional
path — coach does not special-case repo rules in the filter.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from atdd.coach.validators._violation import Violation


@pytest.fixture()
def worktree_with_repo_marker(tmp_path: Path) -> Path:
    """Create a worktree with a repo-rule violation + suppression marker."""
    src = tmp_path / "src" / "example.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    future = date.today() + timedelta(days=90)
    src.write_text(
        f"# atdd:suppress(repo.test-wagon.C001-acc-unit-002) UNTIL={future.isoformat()}\n"
        "x = 1\n",
        encoding="utf-8",
    )
    return tmp_path


class TestRepoRuleViolationNeverSuppressed:
    """C001-UNIT-002: repo.* violations bypass suppression entirely."""

    def test_repo_rule_stays_active_with_marker(
        self, worktree_with_repo_marker: Path
    ):
        """A repo.* violation with a matching marker stays in the active set."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        violations = [
            Violation(
                rule_id="repo.test-wagon.C001-acc-unit-002",
                severity=4,
                location="src/example.py:1",
                detail="repo rule violation",
            ),
        ]
        result = apply_suppression(
            violations, worktree_with_repo_marker, "deadbeef"
        )
        assert len(result.active) == 1
        assert result.active[0].rule_id.startswith("repo.")

    def test_repo_rule_not_in_suppressed_jsonl(
        self, worktree_with_repo_marker: Path
    ):
        """suppressed.jsonl has zero records with repo.* rule_id."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        violations = [
            Violation(
                rule_id="repo.test-wagon.C001-acc-unit-002",
                severity=4,
                location="src/example.py:1",
                detail="repo rule violation",
            ),
        ]
        result = apply_suppression(
            violations, worktree_with_repo_marker, "deadbeef"
        )
        repo_in_suppressed = [
            s for s in result.suppressed if s.rule_id.startswith("repo.")
        ]
        assert len(repo_in_suppressed) == 0

    def test_mixed_violations_repo_stays_toolkit_absorbed(self, tmp_path: Path):
        """Mixed violations: repo stays active, toolkit with marker is absorbed."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        future = date.today() + timedelta(days=90)
        src = tmp_path / "src" / "mixed.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(
            f"# atdd:suppress(coder.logging.coach-silent-swallow) UNTIL={future.isoformat()}\n"
            f"# atdd:suppress(repo.test-wagon.C001-acc-unit-002) UNTIL={future.isoformat()}\n"
            "x = 1\n",
            encoding="utf-8",
        )

        violations = [
            Violation(
                rule_id="coder.logging.coach-silent-swallow",
                severity=4,
                location="src/mixed.py:1",
                detail="silent swallow",
            ),
            Violation(
                rule_id="repo.test-wagon.C001-acc-unit-002",
                severity=4,
                location="src/mixed.py:2",
                detail="repo violation",
            ),
        ]
        result = apply_suppression(violations, tmp_path, "deadbeef")

        active_ids = [v.rule_id for v in result.active]
        suppressed_ids = [v.rule_id for v in result.suppressed]

        assert "repo.test-wagon.C001-acc-unit-002" in active_ids
        assert "coder.logging.coach-silent-swallow" not in active_ids
        assert "coder.logging.coach-silent-swallow" in suppressed_ids
        assert "repo.test-wagon.C001-acc-unit-002" not in suppressed_ids
