# URN: test:consolidate-coach-workspace:canonical-coach-surface:D001-UNIT-001-split-ratio-is-fixed-fifty-fifty
# Acceptance: acc:consolidate-coach-workspace:D001-UNIT-001-split-ratio-is-fixed-fifty-fifty
# WMBT: wmbt:consolidate-coach-workspace:D001
# Phase: RED
# Layer: domain
# Runtime: python
# Assertion: behavioral
"""D001-UNIT-001 — the coach workspace layout policy returns a fixed 50/50
split ratio, independent of worker count.

RED: there is no workspace-layout policy. ``--multiplexer-mode pane`` re-tiles
the workspace as workers are added, shrinking the coach's half. This test pins
``coach_workspace_layout`` — a pure helper returning a 0.5 / 0.5 split for any
worker count.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_split_ratio_is_fixed_fifty_fifty():
    """The coach/worker split is 0.5 / 0.5 for 1, 5, and 20 workers alike."""
    from atdd.coach.utils import session_naming

    layout_fn = getattr(session_naming, "coach_workspace_layout", None)
    assert layout_fn is not None, (
        "session_naming.coach_workspace_layout is not implemented — there is "
        "no fixed coach/worker split policy (RED)"
    )

    ratios = {}
    for worker_count in (1, 5, 20):
        layout = layout_fn(worker_count)
        assert hasattr(layout, "coach_ratio") and hasattr(layout, "worker_ratio"), (
            f"layout for {worker_count} workers must expose coach_ratio and "
            f"worker_ratio; got {layout!r}"
        )
        assert layout.coach_ratio == 0.5, (
            f"coach pane ratio is {layout.coach_ratio} for {worker_count} "
            f"workers; expected a fixed 0.5"
        )
        assert layout.worker_ratio == 0.5, (
            f"worker pane ratio is {layout.worker_ratio} for {worker_count} "
            f"workers; expected a fixed 0.5"
        )
        ratios[worker_count] = (layout.coach_ratio, layout.worker_ratio)

    assert len(set(ratios.values())) == 1, (
        f"the split ratio varies with worker count: {ratios} — it must be fixed"
    )
