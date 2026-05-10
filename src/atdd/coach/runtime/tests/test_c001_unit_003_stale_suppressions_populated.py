# URN: test:dispatch-validators:stale-suppressions-populated
# Acceptance: acc:dispatch-validators:C001-UNIT-003-stale-suppressions-populated
# WMBT: wmbt:dispatch-validators:C001
# Phase: GREEN
# Layer: domain

"""AC-UNIT-003: stale suppression markers populate stale-suppressions.jsonl.

A worktree with at least one ``# atdd:suppress(<rule_id>) [UNTIL=YYYY-MM-DD]``
marker whose ``UNTIL`` date is in the past produces
``.atdd/runtime/validations/<sha>/stale-suppressions.jsonl`` containing one
record per stale marker with ``rule_id``, ``location``, parsed ``UNTIL`` date,
and marker text; no stale-marker record is dropped.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from atdd.coach.validators._violation import Violation


@pytest.fixture()
def worktree_with_stale_marker(tmp_path: Path) -> Path:
    """Create a worktree with a stale (past-UNTIL) suppression marker."""
    past = date.today() - timedelta(days=10)
    src = tmp_path / "src" / "stale.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        f"# atdd:suppress(coder.dead-code.reachability) UNTIL={past.isoformat()}\n"
        "x = 1\n",
        encoding="utf-8",
    )
    return tmp_path


class TestStaleSuppressionsPopulated:
    """C001-UNIT-003: stale markers produce stale-suppressions.jsonl."""

    def test_stale_jsonl_written(self, worktree_with_stale_marker: Path):
        """stale-suppressions.jsonl exists after apply_suppression."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        violations = [
            Violation(
                rule_id="coder.dead-code.reachability",
                severity=3,
                location="src/stale.py:1",
                detail="dead code",
            ),
        ]
        apply_suppression(violations, worktree_with_stale_marker, "deadbeef")
        stale_path = (
            worktree_with_stale_marker / ".atdd" / "runtime" / "validations"
            / "deadbeef" / "stale-suppressions.jsonl"
        )
        assert stale_path.exists()

    def test_stale_record_fields(self, worktree_with_stale_marker: Path):
        """Each stale record carries rule_id, location, until, marker_text."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        past = date.today() - timedelta(days=10)
        violations = [
            Violation(
                rule_id="coder.dead-code.reachability",
                severity=3,
                location="src/stale.py:1",
                detail="dead code",
            ),
        ]
        result = apply_suppression(violations, worktree_with_stale_marker, "deadbeef")
        stale_path = (
            worktree_with_stale_marker / ".atdd" / "runtime" / "validations"
            / "deadbeef" / "stale-suppressions.jsonl"
        )
        lines = stale_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["rule_id"] == "coder.dead-code.reachability"
        assert "location" in record
        assert record.get("until") == past.isoformat()
        assert "marker_text" in record

    def test_multiple_stale_markers_all_recorded(self, tmp_path: Path):
        """Multiple stale markers produce one record each — no losses."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        past1 = date.today() - timedelta(days=5)
        past2 = date.today() - timedelta(days=30)
        src = tmp_path / "src" / "multi_stale.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(
            f"# atdd:suppress(coder.dead-code.reachability) UNTIL={past1.isoformat()}\n"
            f"# atdd:suppress(coder.logging.coach-silent-swallow) UNTIL={past2.isoformat()}\n"
            "x = 1\n",
            encoding="utf-8",
        )

        violations: list = []
        result = apply_suppression(violations, tmp_path, "abc123")
        stale_path = (
            tmp_path / ".atdd" / "runtime" / "validations"
            / "abc123" / "stale-suppressions.jsonl"
        )
        lines = stale_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        rule_ids = {json.loads(line)["rule_id"] for line in lines}
        assert "coder.dead-code.reachability" in rule_ids
        assert "coder.logging.coach-silent-swallow" in rule_ids

    def test_future_marker_not_in_stale(self, tmp_path: Path):
        """A future-UNTIL marker does NOT appear in stale-suppressions.jsonl."""
        from atdd.coach.runtime.suppression_filter import apply_suppression

        future = date.today() + timedelta(days=90)
        src = tmp_path / "src" / "future.py"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(
            f"# atdd:suppress(coder.dead-code.reachability) UNTIL={future.isoformat()}\n"
            "x = 1\n",
            encoding="utf-8",
        )

        violations: list = []
        result = apply_suppression(violations, tmp_path, "abc123")
        stale_path = (
            tmp_path / ".atdd" / "runtime" / "validations"
            / "abc123" / "stale-suppressions.jsonl"
        )
        if stale_path.exists():
            lines = stale_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 0
