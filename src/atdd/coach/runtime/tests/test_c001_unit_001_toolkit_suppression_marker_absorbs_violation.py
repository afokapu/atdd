# URN: test:dispatch-validators:toolkit-suppression-marker-absorbs-violation
# Acceptance: acc:dispatch-validators:C001-UNIT-001-toolkit-suppression-marker-absorbs-violation
# WMBT: wmbt:dispatch-validators:C001
# Phase: GREEN
# Layer: domain

"""AC-UNIT-001: suppress-and-clean toolkit violation with matching marker is absorbed.

A suppress-and-clean toolkit violation with a matching marker
(`# atdd:suppress(<rule_id>) [UNTIL=YYYY-MM-DD]` with future UNTIL date)
on the offending file/line is removed from the active set and appended to
``.atdd/runtime/validations/<sha>/suppressed.jsonl``; the suppressed.jsonl
record carries ``rule_id``, ``location``, marker text, and ``UNTIL`` date.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from atdd.coach.validators._violation import Violation


@pytest.fixture()
def worktree_with_marker(tmp_path: Path) -> Path:
    """Create a worktree with a suppress-and-clean violation + matching marker."""
    src = tmp_path / "src" / "example.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    future = date.today() + timedelta(days=90)
    src.write_text(
        f"# atdd:suppress(coder.logging.coach-silent-swallow) UNTIL={future.isoformat()}\n"
        "x = 1\n",
        encoding="utf-8",
    )
    return tmp_path


class TestToolkitSuppressionAbsorbsViolation:
    """C001-UNIT-001: matching suppress-and-clean marker absorbs the violation."""

    def test_violation_removed_from_active_set(self, worktree_with_marker: Path):
        """The matched violation is not in the active set."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        future = date.today() + timedelta(days=90)
        violations = [
            Violation(
                rule_id="coder.logging.coach-silent-swallow",
                severity=3,
                location="src/example.py:1",
                detail="silent swallow detected",
            ),
        ]
        result = apply_suppression(violations, worktree_with_marker, "deadbeef")
        active_ids = [v.rule_id for v in result.active]
        assert "coder.logging.coach-silent-swallow" not in active_ids

    def test_violation_in_suppressed_set(self, worktree_with_marker: Path):
        """The matched violation appears in the suppressed list."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        future = date.today() + timedelta(days=90)
        violations = [
            Violation(
                rule_id="coder.logging.coach-silent-swallow",
                severity=3,
                location="src/example.py:1",
                detail="silent swallow detected",
            ),
        ]
        result = apply_suppression(violations, worktree_with_marker, "deadbeef")
        assert len(result.suppressed) == 1
        assert result.suppressed[0].rule_id == "coder.logging.coach-silent-swallow"

    def test_suppressed_jsonl_written(self, worktree_with_marker: Path):
        """suppressed.jsonl is written with rule_id, location, marker_text, until."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        future = date.today() + timedelta(days=90)
        violations = [
            Violation(
                rule_id="coder.logging.coach-silent-swallow",
                severity=3,
                location="src/example.py:1",
                detail="silent swallow detected",
            ),
        ]
        result = apply_suppression(violations, worktree_with_marker, "deadbeef")
        suppressed_path = (
            worktree_with_marker / ".atdd" / "runtime" / "validations"
            / "deadbeef" / "suppressed.jsonl"
        )
        assert suppressed_path.exists()
        lines = suppressed_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["rule_id"] == "coder.logging.coach-silent-swallow"
        assert record["location"] == "src/example.py:1"
        assert "marker_text" in record
        assert record.get("until") == future.isoformat()

    def test_unmatched_violation_stays_active(self, tmp_path: Path):
        """A violation with no matching marker stays in the active set."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        src = tmp_path / "src" / "clean.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("x = 1\n", encoding="utf-8")

        violations = [
            Violation(
                rule_id="coder.dead-code.reachability",
                severity=3,
                location="src/clean.py:1",
                detail="dead code",
            ),
        ]
        result = apply_suppression(violations, tmp_path, "abc123")
        assert len(result.active) == 1
        assert result.active[0].rule_id == "coder.dead-code.reachability"
        assert len(result.suppressed) == 0

    def test_expired_until_not_absorbed(self, tmp_path: Path):
        """A marker with past UNTIL does NOT absorb the violation."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        past = date.today() - timedelta(days=10)
        src = tmp_path / "src" / "expired.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(
            f"# atdd:suppress(coder.logging.coach-silent-swallow) UNTIL={past.isoformat()}\n"
            "x = 1\n",
            encoding="utf-8",
        )

        violations = [
            Violation(
                rule_id="coder.logging.coach-silent-swallow",
                severity=3,
                location="src/expired.py:1",
                detail="silent swallow detected",
            ),
        ]
        result = apply_suppression(violations, tmp_path, "abc123")
        assert len(result.active) == 1
        assert len(result.suppressed) == 0
