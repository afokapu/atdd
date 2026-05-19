# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E013-UNIT-003-new-aborts-on-match-without-no-dup-check
# Acceptance: acc:govern-lifecycle:E013-UNIT-003-new-aborts-on-match-without-no-dup-check
# WMBT: wmbt:govern-lifecycle:E013
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E013-UNIT-003 — IssueManager.new() returns 1 and warns when dup found without --no-dup-check."""
from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch


def test_new_aborts_on_match_without_no_dup_check():
    from atdd.coach.commands.issue import IssueManager

    mgr = IssueManager()
    fake_matches = [{"number": 42, "title": "feat(atdd): Existing Slug", "state": "OPEN"}]

    captured = StringIO()
    with patch("atdd.coach.commands.issue.dup_check_before_file", return_value=fake_matches):
        with patch("sys.stdout", captured):
            result = mgr.new(slug="existing-slug", no_dup_check=False)

    output = captured.getvalue()
    assert result == 1, f"expected exit code 1, got {result}"
    assert "42" in output or "existing" in output.lower(), f"expected match info in output: {output!r}"
    assert "--no-dup-check" in output, f"expected bypass hint in output: {output!r}"
