# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-004-filter-modes-and-menu
# Acceptance: acc:coach-ops:M002-UNIT-004-filter-modes-and-menu
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""Single-key filter modes and the in-dashboard menu (pure, no TTY)."""
from __future__ import annotations

from atdd.coach.runtime.dashboard import FILTER_KEYS, WorkerCard, filter_cards, render_card, render_menu


def _c(issue, phase, *, live=True, stalled=False, idle=""):
    return WorkerCard(issue=issue, title="", phase=phase, role="coder",
                      elapsed="1m", live=live, stalled=stalled, idle=idle)


def test_filter_live_and_finished_split_on_liveness():
    cards = [_c(1, "GREEN", live=True), _c(2, "RED", live=False), _c(3, "PLANNED", live=True)]
    assert {c.issue for c in filter_cards(cards, "live")} == {1, 3}
    assert {c.issue for c in filter_cards(cards, "finished")} == {2}


def test_filter_stalled_and_phase():
    cards = [_c(1, "RED", stalled=True), _c(2, "GREEN"), _c(3, "GREEN")]
    assert [c.issue for c in filter_cards(cards, "stalled")] == [1]
    assert {c.issue for c in filter_cards(cards, "phase", phase="GREEN")} == {2, 3}


def test_menu_lists_every_key_and_highlights_active_mode():
    m = render_menu("finished", color=True)
    for key, _, _ in FILTER_KEYS:
        assert f"[{key}]" in m
    assert "[l]" in m and "[f]" in m and "Live" in m and "Finished" in m
    assert "Blocked" not in m  # removed
    assert "\x1b[7m" in m  # active mode in reverse video


def test_menu_phase_entry_shows_current_phase():
    assert "Phase:RED" in render_menu("phase", phase="RED", color=False)


def test_live_worker_shows_uptime_finished_shows_ran_and_ended():
    live = WorkerCard(issue=1, title="", phase="RED", role="coder",
                      elapsed="14m04s", live=True)
    done = WorkerCard(issue=2, title="", phase="REFACTOR", role="coder",
                      elapsed="30m00s", idle="2d", live=False)
    a = "\n".join(render_card(live, width=44))
    b = "\n".join(render_card(done, width=44))
    assert "up 14m04s" in a and "ran" not in a
    assert "ran 30m00s" in b and "ended 2d ago" in b and "up " not in b
