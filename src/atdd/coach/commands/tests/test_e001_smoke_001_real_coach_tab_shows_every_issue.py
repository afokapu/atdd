# URN: test:consolidate-coach-workspace:canonical-coach-surface:E001-SMOKE-001-real-coach-tab-shows-every-issue
# Acceptance: acc:consolidate-coach-workspace:E001-SMOKE-001-real-coach-tab-shows-every-issue
# WMBT: wmbt:consolidate-coach-workspace:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E001-SMOKE-001 — against a real coach run, the single coach tab displays a
per-issue status line for every managed issue.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Delivered at RED to bind the
``E001-SMOKE-001`` acceptance; exercised at the GREEN→SMOKE transition.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real coach",
    ),
]


def test_real_coach_tab_shows_every_issue():
    """The canonical coach tab on a real multiplexer shows one status line per
    managed issue, each displaying that issue's current phase."""
    from atdd.coach.commands import coach
    from atdd.coach.utils.multiplexer import get_multiplexer

    render = getattr(coach, "render_consolidated_view", None)
    assert render is not None, "coach.render_consolidated_view not implemented"

    mx = get_multiplexer()
    config = {"repo": {"short_name": "ATDD"}}
    records = [
        {"issue": 736, "phase": "PLANNED", "last_decision": "spawned-planner", "worker_health": "healthy"},
        {"issue": 601, "phase": "RED",     "last_decision": "tests-written",   "worker_health": "healthy"},
    ]

    render(mx, config, records)

    coach_panes = [p for p in mx.list_panes() if p["name"] == "ATDD-coach"]
    assert len(coach_panes) == 1, f"expected one canonical coach tab; got {coach_panes}"

    screen = mx.read_screen(coach_panes[0]["ref"], lines=200)
    for rec in records:
        assert f"#{rec['issue']}" in screen, f"coach tab omits issue #{rec['issue']}"
        assert rec["phase"] in screen, f"coach tab omits phase for #{rec['issue']}"
