# URN: test:consolidate-coach-workspace:canonical-coach-surface:Y001-SMOKE-001-real-multiplexer-shows-one-coach-tab
# Acceptance: acc:consolidate-coach-workspace:Y001-SMOKE-001-real-multiplexer-shows-one-coach-tab
# WMBT: wmbt:consolidate-coach-workspace:Y001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y001-SMOKE-001 — against a real multiplexer, orchestrating two issues
produces exactly one coach tab.

Opt-in: this SMOKE test drives a real cmux/tmux backend and is skipped unless
``ATDD_RUN_SMOKE=1`` is set. It is delivered at RED to bind the
``Y001-SMOKE-001`` acceptance; it is exercised at the GREEN→SMOKE transition.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real multiplexer",
    ),
]


def test_real_multiplexer_shows_one_coach_tab():
    """Two coach orchestrations against a real multiplexer leave exactly one
    tab matching the canonical coach name and no per-issue `ATDD-coach-<N>` tab."""
    from atdd.coach.commands import coach
    from atdd.coach.utils.multiplexer import get_multiplexer

    resolve = getattr(coach, "resolve_or_create_coach_surface", None)
    assert resolve is not None, "coach.resolve_or_create_coach_surface not implemented"

    mx = get_multiplexer()
    config = {"repo": {"short_name": "ATDD"}}

    resolve(mx, config, 736)
    resolve(mx, config, 601)

    names = [p["name"] for p in mx.list_panes()]
    coach_tabs = [n for n in names if n == "ATDD-coach"]
    per_issue = [n for n in names if isinstance(n, str) and n.startswith("ATDD-coach-")]

    assert len(coach_tabs) == 1, (
        f"expected exactly one canonical coach tab; found {coach_tabs}"
    )
    assert per_issue == [], (
        f"per-issue coach tabs present on a real multiplexer: {per_issue}"
    )
