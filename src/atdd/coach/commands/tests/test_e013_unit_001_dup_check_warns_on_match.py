# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E013-UNIT-001-dup-check-warns-on-match
# Acceptance: acc:govern-lifecycle:E013-UNIT-001-dup-check-warns-on-match
# WMBT: wmbt:govern-lifecycle:E013
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E013-UNIT-001 — dup_check_before_file returns matches when gh finds similar issues."""
from __future__ import annotations

import json


def _make_gh_result(issues: list) -> object:
    class _Result:
        stdout = json.dumps(issues)
        returncode = 0

    return _Result()


def test_dup_check_warns_on_match():
    from atdd.coach.commands.issue import dup_check_before_file

    fake_issues = [{"number": 42, "title": "feat(atdd): Some Similar Title", "state": "OPEN"}]

    def _mock_gh(slug):
        return _make_gh_result(fake_issues)

    matches = dup_check_before_file(slug="some-similar-title", run_gh=_mock_gh)
    assert len(matches) > 0, "expected at least one match"
    assert "number" in matches[0]
    assert "title" in matches[0]
