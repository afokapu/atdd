# URN: test:govern-lifecycle:smoke-false-green-prevention:M002-UNIT-001-smoke-audit-has-future-tracking-section
# Acceptance: acc:govern-lifecycle:M002-UNIT-001-smoke-audit-has-future-tracking-section
# WMBT: wmbt:govern-lifecycle:M002
# Phase: RED
# Layer: unit
# Assertion: structural
"""
RED: docs/smoke-audit.md must contain a Future-Tracking (or Regression Metric)
section with columns release-wave, post-SMOKE-bugs, expectation, and at least
one row for v3.83.x with expectation=0.  Currently fails because
docs/smoke-audit.md does not yet exist.
"""
from __future__ import annotations

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner, pytest.mark.platform]

_AUDIT_PATH = find_repo_root() / "docs" / "smoke-audit.md"
_REQUIRED_SECTION_TERMS = ["release-wave", "post-SMOKE-bugs", "expectation"]
_SECTION_HEADERS = ["## Future Tracking", "## Regression Metric", "## future tracking", "## regression metric"]


def test_smoke_audit_has_future_tracking_section():
    """docs/smoke-audit.md must contain a Future-Tracking or Regression-Metric section."""
    assert _AUDIT_PATH.exists(), (
        f"docs/smoke-audit.md not found at {_AUDIT_PATH}. "
        "Create it with the E027 GREEN phase (includes classification table + Future-Tracking section)."
    )
    content = _AUDIT_PATH.read_text()
    has_section = any(h.lower() in content.lower() for h in _SECTION_HEADERS)
    assert has_section, (
        "docs/smoke-audit.md is missing a '## Future Tracking' or '## Regression Metric' section. "
        "Add a section with columns: release-wave | post-SMOKE-bugs | expectation."
    )


def test_smoke_audit_future_tracking_has_required_columns():
    """The Future-Tracking section must have release-wave, post-SMOKE-bugs, and expectation columns."""
    if not _AUDIT_PATH.exists():
        pytest.skip("docs/smoke-audit.md not yet created — see test_smoke_audit_has_future_tracking_section")
    content = _AUDIT_PATH.read_text()
    for col in _REQUIRED_SECTION_TERMS:
        assert col in content, (
            f"docs/smoke-audit.md Future-Tracking section is missing column '{col}'. "
            "Add a table with columns: release-wave | post-SMOKE-bugs | expectation."
        )


def test_smoke_audit_future_tracking_has_v383_row():
    """The Future-Tracking section must have at least one row for v3.83.x with expectation=0."""
    if not _AUDIT_PATH.exists():
        pytest.skip("docs/smoke-audit.md not yet created — see test_smoke_audit_has_future_tracking_section")
    content = _AUDIT_PATH.read_text()
    has_v383 = "v3.83" in content or "3.83" in content
    assert has_v383, (
        "docs/smoke-audit.md Future-Tracking section must include a row for the v3.83.x wave. "
        "Set expectation=0 to establish the baseline post-retrofit regression metric."
    )
