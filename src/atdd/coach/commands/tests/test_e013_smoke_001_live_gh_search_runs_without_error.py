# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E013-SMOKE-001-live-gh-search-runs-without-error
# Acceptance: acc:govern-lifecycle:E013-SMOKE-001-live-gh-search-runs-without-error
# WMBT: wmbt:govern-lifecycle:E013
# Phase: SMOKE
# Layer: backend.integration
# Assertion: behavioral

"""acc:govern-lifecycle:E013-SMOKE-001 — dup_check_before_file runs live gh issue list without raising."""
from __future__ import annotations

import os
import pytest


@pytest.mark.integration
def test_live_gh_search_runs_without_error():
    if not os.environ.get("GITHUB_TOKEN"):
        pytest.skip("GITHUB_TOKEN not set — skipping live gh integration test")

    from atdd.coach.commands.issue import dup_check_before_file

    result = dup_check_before_file(slug="atdd-smoke-test-unique-slug-xyz-e013")
    assert isinstance(result, list), f"expected list, got {type(result)}"
