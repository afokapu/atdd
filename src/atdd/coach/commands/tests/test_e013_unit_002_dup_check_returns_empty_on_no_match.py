# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E013-UNIT-002-dup-check-returns-empty-on-no-match
# Acceptance: acc:govern-lifecycle:E013-UNIT-002-dup-check-returns-empty-on-no-match
# WMBT: wmbt:govern-lifecycle:E013
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E013-UNIT-002 — dup_check_before_file returns empty list when no matches found."""
from __future__ import annotations

import json


def _make_gh_result(issues: list) -> object:
    class _Result:
        stdout = json.dumps(issues)
        returncode = 0

    return _Result()


def test_dup_check_returns_empty_on_no_match():
    from atdd.coach.commands.issue import dup_check_before_file

    def _mock_gh(slug):
        return _make_gh_result([])

    matches = dup_check_before_file(slug="unique-slug-no-match", run_gh=_mock_gh)
    assert matches == [], f"expected empty list, got {matches}"
