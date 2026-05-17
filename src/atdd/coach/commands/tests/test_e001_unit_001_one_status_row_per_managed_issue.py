# URN: test:consolidate-coach-workspace:canonical-coach-surface:E001-UNIT-001-one-status-row-per-managed-issue
# Acceptance: acc:consolidate-coach-workspace:E001-UNIT-001-one-status-row-per-managed-issue
# WMBT: wmbt:consolidate-coach-workspace:E001
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E001-UNIT-001 — the consolidated-view builder emits exactly one status row
per managed issue, each row naming phase, last decision, and worker health.

RED: there is no consolidated coach view. The operator sees one raw `atdd
coach` process terminal per invocation. This test pins
``coach.build_consolidated_view`` — a builder that turns a list of managed-issue
state records into a single per-issue status surface.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


_RECORDS = [
    {"issue": 736, "phase": "PLANNED",  "last_decision": "spawned-planner",  "worker_health": "healthy"},
    {"issue": 601, "phase": "RED",      "last_decision": "tests-written",    "worker_health": "healthy"},
    {"issue": 730, "phase": "REFACTOR", "last_decision": "architecture-ok",  "worker_health": "degraded"},
]


def test_one_status_row_per_managed_issue():
    """Three managed issues render to exactly three status rows, each naming
    issue / phase / last decision / worker health — and no raw coach stdout."""
    from atdd.coach.commands import coach

    build = getattr(coach, "build_consolidated_view", None)
    assert build is not None, (
        "coach.build_consolidated_view is not implemented — there is no "
        "consolidated multi-issue status view (RED)"
    )

    view = build(_RECORDS)
    assert isinstance(view, str), f"expected a rendered string view, got {type(view)}"

    lines = view.splitlines()
    for rec in _RECORDS:
        rows = [ln for ln in lines if f"#{rec['issue']}" in ln]
        assert len(rows) == 1, (
            f"issue #{rec['issue']} appears on {len(rows)} rows; expected exactly one"
        )
        row = rows[0]
        assert rec["phase"] in row, f"row for #{rec['issue']} omits phase {rec['phase']!r}"
        assert rec["last_decision"] in row, (
            f"row for #{rec['issue']} omits last decision {rec['last_decision']!r}"
        )
        assert rec["worker_health"] in row, (
            f"row for #{rec['issue']} omits worker health {rec['worker_health']!r}"
        )

    assert "atdd coach" not in view.lower(), (
        "consolidated view leaks a raw `atdd coach` process stdout line"
    )
