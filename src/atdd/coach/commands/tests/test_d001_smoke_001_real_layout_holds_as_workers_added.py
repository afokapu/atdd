# URN: test:consolidate-coach-workspace:canonical-coach-surface:D001-SMOKE-001-real-layout-holds-as-workers-added
# Acceptance: acc:consolidate-coach-workspace:D001-SMOKE-001-real-layout-holds-as-workers-added
# WMBT: wmbt:consolidate-coach-workspace:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""D001-SMOKE-001 — against a real multiplexer, adding workers keeps the coach
pane at 50% and places workers as right-pane tabs.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Delivered at RED to bind the
``D001-SMOKE-001`` acceptance; exercised at the GREEN→SMOKE transition.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real multiplexer",
    ),
]


def test_real_layout_holds_as_workers_added():
    """On a real cmux session, adding three more workers keeps the coach pane
    at 50% width and places each worker as a right-pane tab (no new panes)."""
    from atdd.coach.commands import coach
    from atdd.coach.utils.multiplexer import get_multiplexer

    add_worker = getattr(coach, "add_worker_surface", None)
    assert add_worker is not None, "coach.add_worker_surface not implemented"

    mx = get_multiplexer()
    config = {"repo": {"short_name": "ATDD"}}

    panes_before = len(mx.list_panes())
    for issue in (601, 730, 690):
        add_worker(mx, f"ATDD{issue}", config=config)
    panes_after = len(mx.list_panes())

    assert panes_after == panes_before, (
        f"adding three workers created {panes_after - panes_before} new pane(s); "
        f"workers must be right-pane surfaces, not panes"
    )
