# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-003-card-presentation
# Acceptance: acc:coach-ops:M002-UNIT-003-card-presentation
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""render_card draws a single worker as a fixed-width box: title, phase tint,
progress bar, surface id, and a colored state dot — all width-preserving."""
from __future__ import annotations

import re

from atdd.coach.runtime.dashboard import (
    WorkerCard,
    _progress_bar,
    render_card,
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _visible(s: str) -> str:
    return _ANSI.sub("", s)


def _card(issue, phase="RED", role="coder"):
    return WorkerCard(issue=issue, title="", phase=phase, role=role, started="01:00", last="10:41")


def test_render_card_is_a_box_of_fixed_width():
    lines = render_card(_card(1036), width=21)
    assert lines[0].startswith("┌") and lines[0].endswith("┐")
    assert lines[-1].startswith("└") and lines[-1].endswith("┘")
    assert all(len(line) == 21 for line in lines)
    assert any("#1036" in line for line in lines)
    assert any("RED" in line for line in lines)


def test_paused_card_shows_warning_glyph():
    c = WorkerCard(issue=1030, title="", phase="PLANNED", role="planner",
                   started="01:00", last="10:41", state="paused")
    assert any("⚠" in line for line in render_card(c, width=21))


def test_progress_bar_tracks_lifecycle_position():
    # 7 stages × 3 cells = 21 cells; filled = (stage index + 1) × 3.
    assert _progress_bar("INIT") == "▰▰▰" + "▱" * 18
    assert _progress_bar("GREEN") == "▰" * 12 + "▱" * 9
    assert _progress_bar("COMPLETE") == "▰" * 21
    assert _progress_bar("BLOCKED") == "▱" * 21
    assert _progress_bar("?") == ""  # unknown phase → no bar


def test_card_includes_progress_bar_row():
    rendered = "\n".join(render_card(_card(1, phase="RED"), width=30))
    assert "▰" * 9 + "▱" in rendered  # RED is the 3rd of 7 stages → 9/21 filled


def test_card_renders_issue_title_when_present():
    c = WorkerCard(issue=1036, title="Declared Dispatch Registry",
                   phase="GREEN", role="coder", started="01:00", last="10:41")
    rendered = "\n".join(render_card(c, width=28))
    assert "Declared Dispatch" in rendered


def test_color_tints_phase_and_preserves_visible_width():
    c = _card(1036, phase="GREEN")
    plain = render_card(c, width=21, color=False)
    colored = render_card(c, width=21, color=True)
    # No escapes when color is off.
    assert all("\x1b[" not in ln for ln in plain)
    # GREEN's GitHub label color (#0E8A16 → 14;138;22) is present when on.
    assert any("\x1b[38;2;14;138;22m" in ln for ln in colored)
    # Tinting wraps padded content, so visible width is unchanged.
    assert all(len(_visible(ln)) == 21 for ln in colored)


def test_card_shows_surface_id_to_distinguish_same_issue_workers():
    # Two workers on the SAME issue must be tellable apart by their cmux surface.
    a = WorkerCard(issue=1036, title="", phase="GREEN", role="coder",
                   started="01:00", last="10:41", surface="surface:623")
    b = WorkerCard(issue=1036, title="", phase="SMOKE", role="tester",
                   started="01:00", last="10:41", surface="surface:624")
    ra = "\n".join(render_card(a, width=40))
    rb = "\n".join(render_card(b, width=40))
    assert "coder (623)" in ra and "tester (624)" in rb  # persona (surface)
    assert ra != rb


def test_card_state_dot_is_colored_and_width_preserved():
    live = WorkerCard(issue=1, title="", phase="RED", role="coder", started="01:00", state="live")
    colored = render_card(live, width=44, color=True)
    plain = render_card(live, width=44, color=False)
    assert any("●" in ln for ln in plain)
    assert any("\x1b[38;2;14;138;22m●" in ln for ln in colored)  # green dot
    assert all(len(_visible(ln)) == 44 for ln in colored)        # box stays aligned
