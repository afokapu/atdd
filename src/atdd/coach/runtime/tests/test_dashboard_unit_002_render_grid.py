# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-002-grid-reflows-and-clamps
# Acceptance: acc:coach-ops:M002-UNIT-002-grid-reflows-and-clamps
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""render_grid reflows cards to the terminal width, clamps to the viewport,
and paginates — card-internal presentation lives in the UNIT-003 sibling."""
from __future__ import annotations

from atdd.coach.runtime.dashboard import WorkerCard, render_grid


def _card(issue, phase="RED", role="coder"):
    return WorkerCard(issue=issue, title="", phase=phase, role=role, started="01:00", last="10:41")


def test_grid_uses_one_column_when_narrow():
    cards = [_card(i) for i in (1, 2, 3)]
    out = render_grid(cards, term_width=24, card_width=21)
    # 3 stacked cards, each box is 8+ lines; no two boxes share a row.
    top_rows = [ln for ln in out.splitlines() if ln.startswith("┌")]
    assert len(top_rows) == 3
    assert all(row.count("┌") == 1 for row in top_rows)


def test_grid_packs_multiple_columns_when_wide():
    cards = [_card(i) for i in (1, 2, 3, 4)]
    out = render_grid(cards, term_width=90, card_width=21)
    top_rows = [ln for ln in out.splitlines() if ln.startswith("┌")]
    # 4 cards at 21w into 90w → 4 per row → a single row of tops with 4 boxes.
    assert any(row.count("┌") >= 2 for row in top_rows)


def test_empty_grid_has_a_message():
    assert "No active workers" in render_grid([], term_width=80)


def test_grid_clamps_to_max_lines_and_shows_more_footer():
    cards = [_card(i) for i in range(40)]
    out = render_grid(cards, term_width=24, card_width=21, max_lines=10)
    lines = out.splitlines()
    assert len(lines) <= 10  # never overflows the viewport
    assert "more" in lines[-1]  # hidden-count footer present


def test_grid_color_flag_threads_to_cards():
    out = render_grid([_card(1, phase="SMOKE")], term_width=24, card_width=21, color=True)
    assert "\x1b[38;2;29;118;219m" in out  # SMOKE #1D76DB


def test_paginate_windows_and_clamps():
    from atdd.coach.runtime.dashboard import paginate

    lines = [str(i) for i in range(25)]
    assert paginate(lines, 0, 10) == ([str(i) for i in range(10)], 0, 3)
    assert paginate(lines, 1, 10) == ([str(i) for i in range(10, 20)], 1, 3)
    w, page, pages = paginate(lines, 99, 10)  # over-shoot clamps to last page
    assert page == 2 and w == [str(i) for i in range(20, 25)]
