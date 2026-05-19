# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E013-UNIT-004-new-proceeds-with-no-dup-check-flag
# Acceptance: acc:govern-lifecycle:E013-UNIT-004-new-proceeds-with-no-dup-check-flag
# WMBT: wmbt:govern-lifecycle:E013
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E013-UNIT-004 — IssueManager.new() proceeds to creation when no_dup_check=True."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


def test_new_proceeds_with_no_dup_check_flag():
    from atdd.coach.commands.issue import IssueManager

    mgr = IssueManager()
    fake_matches = [{"number": 42, "title": "feat(atdd): Existing Slug", "state": "OPEN"}]

    with patch("atdd.coach.commands.issue.dup_check_before_file", return_value=fake_matches):
        with patch.object(mgr, "_new_github_issue", return_value=0) as mock_create:
            result = mgr.new(slug="existing-slug", no_dup_check=True)

    assert result == 0, f"expected exit code 0 (proceeded), got {result}"
    mock_create.assert_called_once(), "expected _new_github_issue to be called"
