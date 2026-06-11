# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-004-filter-modes-and-menu
# Acceptance: acc:coach-ops:M002-UNIT-004-filter-modes-and-menu
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""Run-state filters (live/stopped) + the orthogonal phase sub-filter and menu."""
from __future__ import annotations

from atdd.coach.runtime.dashboard import (
    Event,
    STATE_KEYS,
    WorkerCard,
    filter_cards,
    render_card,
    render_menu,
)


def _c(issue, phase, *, state="live"):
    return WorkerCard(issue=issue, title="", phase=phase, role="coder",
                      started="01:00", state=state)


def test_filter_by_run_state():
    cards = [_c(1, "GREEN", state="live"), _c(2, "RED", state="stopped"),
             _c(3, "PLANNED", state="live")]
    assert {c.issue for c in filter_cards(cards, "live")} == {1, 3}
    assert {c.issue for c in filter_cards(cards, "stopped")} == {2}
    assert {c.issue for c in filter_cards(cards, "all")} == {1, 2, 3}


def test_state_and_phase_are_orthogonal_and_combine():
    cards = [_c(1, "RED", state="live"), _c(2, "GREEN", state="live"),
             _c(3, "RED", state="stopped")]
    # Live + RED → only #1.
    assert [c.issue for c in filter_cards(cards, "live", phase="RED")] == [1]
    # All + GREEN → only #2.
    assert [c.issue for c in filter_cards(cards, "all", phase="GREEN")] == [2]


def test_menu_lists_states_and_highlights_active():
    m = render_menu("stopped", color=True)
    for key, _, _ in STATE_KEYS:
        assert f"[{key}]" in m
    assert "Live" in m and "Stopped" in m and "All" in m
    assert "Paused" not in m and "Finished" not in m
    assert "\x1b[7m" in m  # active state highlighted


def test_menu_shows_phase_subfilter_row():
    m = render_menu("live", phase="RED", color=False)
    assert "State:" in m and "Phase: RED" in m


def test_state_render_and_events_feed():
    live = WorkerCard(issue=1, title="", phase="RED", role="coder",
                      started="01:00", state="live")
    stopped = WorkerCard(issue=2, title="", phase="REFACTOR", role="coder",
                         started="01:00", state="stopped")
    with_events = WorkerCard(
        issue=3, title="", phase="RED", role="coder", started="01:00", state="live",
        events=[Event(time="11:27", severity="block", text="worker idle — hard-blocked")],
    )
    a = "\n".join(render_card(live, width=44))
    b = "\n".join(render_card(stopped, width=44))
    c = "\n".join(render_card(with_events, width=50))
    assert "● live" in a and "started 01:00" in a and "up " not in a
    assert "● stopped" in b
    assert "channel" in c and "11:27" in c and "hard-blocked" in c


def test_menu_shows_state_emoji():
    m = render_menu("live", color=False)
    assert "🟢" in m and "⚪" in m  # live / stopped emoji in the State row
