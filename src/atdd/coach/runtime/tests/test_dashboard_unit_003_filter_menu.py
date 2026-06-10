# URN: test:coach-ops:coach-dashboard:PLACEHOLDER-UNIT-003-filter-menu
# WMBT: wmbt:coach-ops:PLACEHOLDER   # FIXME(#1053): assign real WMBT id when planner defines WMBTs at PLANNED
# Phase: RED
# Layer: domain
"""Single-key filter modes and the in-dashboard menu (pure, no TTY)."""
from __future__ import annotations

from atdd.coach.runtime.dashboard import FILTER_KEYS, WorkerCard, filter_cards, render_card, render_menu


def _c(issue, phase, *, stalled=False, idle=""):
    return WorkerCard(issue=issue, title="", phase=phase, role="coder",
                      elapsed="1m", stalled=stalled, idle=idle)


def test_filter_active_keeps_only_current_run_issues():
    cards = [_c(1, "GREEN"), _c(2, "RED"), _c(3, "PLANNED")]
    out = filter_cards(cards, "active", active_issues={1, 3})
    assert {c.issue for c in out} == {1, 3}


def test_filter_blocked_and_stalled_and_phase():
    cards = [_c(1, "BLOCKED"), _c(2, "RED", stalled=True), _c(3, "GREEN")]
    assert [c.issue for c in filter_cards(cards, "blocked")] == [1]
    assert [c.issue for c in filter_cards(cards, "stalled")] == [2]
    assert [c.issue for c in filter_cards(cards, "phase", phase="GREEN")] == [3]


def test_filter_historical_returns_everything():
    cards = [_c(1, "GREEN"), _c(2, "RED")]
    assert len(filter_cards(cards, "historical")) == 2


def test_menu_lists_every_key_and_highlights_active_mode():
    m = render_menu("blocked", color=True)
    for key, _, _ in FILTER_KEYS:
        assert f"[{key}]" in m
    assert "\x1b[7m" in m  # active mode in reverse video


def test_menu_status_entry_shows_current_phase():
    assert "Status:RED" in render_menu("phase", phase="RED", color=False)


def test_meta_labels_runtime_up_and_idle_only_when_stalled():
    active = WorkerCard(issue=1, title="", phase="RED", role="coder",
                        elapsed="14m04s", idle="2m", stalled=False)
    stalled = WorkerCard(issue=2, title="", phase="RED", role="coder",
                         elapsed="14m04s", idle="12m", stalled=True)
    a = "\n".join(render_card(active, width=40))
    s = "\n".join(render_card(stalled, width=40))
    assert "up 14m04s" in a and "idle" not in a
    assert "up 14m04s" in s and "idle 12m" in s and "⚠" in s
