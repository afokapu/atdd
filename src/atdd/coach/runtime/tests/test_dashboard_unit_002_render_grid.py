# URN: test:coach-ops:coach-dashboard:PLACEHOLDER-UNIT-002-render-grid
# WMBT: wmbt:coach-ops:PLACEHOLDER   # FIXME(#1053): assign real WMBT id when planner defines WMBTs at PLANNED
# Phase: RED
# Layer: domain
"""render_grid reflows cards to terminal width; render_card draws a box."""
from __future__ import annotations

from atdd.coach.runtime.dashboard import Task, WorkerCard, render_card, render_grid


def _card(issue, phase="RED", role="coder"):
    return WorkerCard(issue=issue, title="", phase=phase, role=role, elapsed="1m00s")


def test_render_card_is_a_box_of_fixed_width():
    lines = render_card(_card(1036), width=21)
    assert lines[0].startswith("┌") and lines[0].endswith("┐")
    assert lines[-1].startswith("└") and lines[-1].endswith("┘")
    assert all(len(line) == 21 for line in lines)
    assert any("#1036" in line for line in lines)
    assert any("RED" in line for line in lines)


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


def test_stalled_card_shows_warning_glyph():
    c = WorkerCard(issue=1030, title="", phase="PLANNED", role="planner",
                   elapsed="14m02s", stalled=True)
    assert any("⚠" in line for line in render_card(c, width=21))


def test_tasks_render_with_progress_footer():
    c = WorkerCard(
        issue=1, title="", phase="RED", role="coder", elapsed="1m",
        tasks=[Task("a", "done"), Task("b", "doing"), Task("c", "todo")],
    )
    rendered = "\n".join(render_card(c, width=24))
    assert "✓" in rendered and "◐" in rendered and "○" in rendered
    assert "1/3" in rendered


def test_empty_grid_has_a_message():
    assert "No active workers" in render_grid([], term_width=80)
