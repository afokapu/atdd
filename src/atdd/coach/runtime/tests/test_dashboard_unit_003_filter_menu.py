# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-004-filter-modes-and-menu
# Acceptance: acc:coach-ops:M002-UNIT-004-filter-modes-and-menu
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""Run-state filters (live/paused/stopped) + the orthogonal phase sub-filter and menu."""
from __future__ import annotations

from atdd.coach.runtime.dashboard import STATE_KEYS, WorkerCard, filter_cards, render_card, render_menu


def _c(issue, phase, *, state="live"):
    return WorkerCard(issue=issue, title="", phase=phase, role="coder",
                      started="01:00", last="10:41", duration="30m", state=state)


def test_filter_by_run_state():
    cards = [_c(1, "GREEN", state="live"), _c(2, "RED", state="paused"),
             _c(3, "PLANNED", state="stopped")]
    assert {c.issue for c in filter_cards(cards, "live")} == {1}
    assert {c.issue for c in filter_cards(cards, "paused")} == {2}
    assert {c.issue for c in filter_cards(cards, "stopped")} == {3}
    assert {c.issue for c in filter_cards(cards, "all")} == {1, 2, 3}


def test_state_and_phase_are_orthogonal_and_combine():
    cards = [
        _c(1, "RED", state="live"), _c(2, "GREEN", state="live"),
        _c(3, "RED", state="paused"),
    ]
    # Live + RED → only #1 (not the paused RED, not the live GREEN).
    assert [c.issue for c in filter_cards(cards, "live", phase="RED")] == [1]
    # All + GREEN → only #2.
    assert [c.issue for c in filter_cards(cards, "all", phase="GREEN")] == [2]


def test_menu_lists_states_and_highlights_active():
    m = render_menu("paused", color=True)
    for key, _, _ in STATE_KEYS:
        assert f"[{key}]" in m
    assert "Live" in m and "Paused" in m and "Stopped" in m and "All" in m
    assert "Finished" not in m and "Stalled" not in m and "Blocked" not in m
    assert "\x1b[7m" in m  # active state highlighted


def test_menu_shows_phase_subfilter_row():
    m = render_menu("live", phase="RED", color=False)
    assert "State:" in m and "Phase: RED" in m


def test_state_specific_timing_render():
    # Absolute clock times only; no growing "time since" counters.
    live = WorkerCard(issue=1, title="", phase="RED", role="coder",
                      started="01:00", last="10:41", state="live")
    paused = WorkerCard(issue=2, title="", phase="RED", role="coder",
                        started="01:00", last="10:26", state="paused")
    stopped = WorkerCard(issue=3, title="", phase="REFACTOR", role="coder",
                         duration="30m00s", last="Jun 9 14:30", state="stopped")
    a = "\n".join(render_card(live, width=44))
    b = "\n".join(render_card(paused, width=44))
    c = "\n".join(render_card(stopped, width=44))
    assert "started 01:00" in a and "last 10:41" in a and "up " not in a and "ago" not in a
    assert "started 01:00" in b and "last 10:26" in b and "⚠" in b
    assert "ran 30m00s" in c and "ended Jun 9 14:30" in c and "up " not in c and "ago" not in c
