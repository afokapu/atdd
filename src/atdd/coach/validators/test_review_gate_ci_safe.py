# URN: test:integration-hardening:integration-hardening:E005-INTEGRATION-002-workflow-no-swallow
# Acceptance: acc:integration-hardening:E005-INTEGRATION-002-workflow-no-swallow
# Acceptance: acc:integration-hardening:E005-INTEGRATION-003-workflow-fallback-consistency
# WMBT: wmbt:integration-hardening:E005
# Phase: RED
# Layer: integration
# Assertion: structural
"""E005 workflow lint tests.

Covers:
- E005-INTEGRATION-002: atdd-review.yml has no '|| true' on the review step
- E005-INTEGRATION-003: both jq invocations use the same fallback value for .verdict
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[4] / ".github" / "workflows" / "atdd-review.yml"
)


def _workflow_text() -> str:
    assert _WORKFLOW_PATH.exists(), (
        f"atdd-review.yml not found at {_WORKFLOW_PATH}; "
        "expected .github/workflows/atdd-review.yml relative to repo root"
    )
    return _WORKFLOW_PATH.read_text()


class TestWorkflowNoSwallow:
    """E005-INTEGRATION-002: review step must not contain '|| true'."""

    def test_review_step_has_no_or_true(self):
        text = _workflow_text()
        assert "|| true" not in text, (
            "atdd-review.yml contains '|| true' — the review step must not swallow "
            "failures; remove '|| true' so regressions are visible"
        )

    def test_in_process_flag_present(self):
        text = _workflow_text()
        assert "--no-spawn" in text or "--in-process" in text, (
            "atdd-review.yml review step must pass --no-spawn or --in-process to "
            "`atdd coach review` so CI runners without cmux can produce a report"
        )


class TestWorkflowFallbackConsistency:
    """E005-INTEGRATION-003: all jq .verdict fallback values must be identical."""

    def test_jq_verdict_fallbacks_are_consistent(self):
        text = _workflow_text()
        pattern = re.compile(r'jq\s+-r\s+[\'"]\.verdict\s*//\s*"([^"]+)"')
        fallbacks = pattern.findall(text)
        assert len(fallbacks) >= 2, (
            f"expected at least 2 jq .verdict calls in atdd-review.yml, found {len(fallbacks)}"
        )
        unique = set(fallbacks)
        assert len(unique) == 1, (
            f"jq .verdict fallback values are inconsistent: {sorted(unique)!r}; "
            "all jq calls reading .verdict must use the same fallback value "
            "(both 'fail' or both 'unknown', never mixed)"
        )

    def test_jq_fallback_value_is_fail(self):
        text = _workflow_text()
        pattern = re.compile(r'jq\s+-r\s+[\'"]\.verdict\s*//\s*"([^"]+)"')
        fallbacks = pattern.findall(text)
        for fb in fallbacks:
            assert fb == "fail", (
                f"jq .verdict fallback should be 'fail' (safer default for enforcement gate), "
                f"got {fb!r}"
            )
