# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E005-SMOKE-001-real-respawn-fresh-process-same-surface
# Acceptance: acc:spawn-agents:E005-SMOKE-001-real-respawn-fresh-process-same-surface
# WMBT: wmbt:spawn-agents:E005
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E005-SMOKE-001 — against a real multiplexer, the respawn primitive kills the
running process and a fresh process is observed in the same surface, leaving no
orphan.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Delivered at RED to bind the
``E005-SMOKE-001`` acceptance; exercised at the GREEN→SMOKE transition.
"""
from __future__ import annotations

import os
import time

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("ATDD_RUN_SMOKE"),
        reason="opt-in SMOKE test — set ATDD_RUN_SMOKE=1 to run against a real multiplexer",
    ),
]


def test_real_respawn_fresh_process_same_surface():
    """A real respawn on a real backend swaps the process in place: the
    original process is gone, a fresh one runs in the same surface, no orphan
    pane is left behind."""
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()

    # A long-lived, observable original process in a fresh surface.
    original_marker = f"e005-original-{os.getpid()}"
    surface_ref = mx.new_workspace(
        cwd=os.getcwd(),
        command=f"sh -c 'echo {original_marker}; sleep 600'",
        name="ATDD746-e005-smoke",
    )
    time.sleep(2)
    surfaces_before = {
        p["ref"] for p in mx.list_panes()
    } if hasattr(mx, "list_panes") else set()

    # Respawn the surface with a distinct replacement process.
    replacement_marker = f"e005-replacement-{os.getpid()}"
    mx.respawn_pane(
        surface_ref,
        command=f"sh -c 'echo {replacement_marker}; sleep 600'",
    )
    time.sleep(2)

    screen = mx.read_screen(surface_ref, lines=200)
    assert replacement_marker in screen, (
        "the fresh replacement process is not running in the surface after "
        f"respawn — screen: {screen!r}"
    )

    # No orphan: the surface count did not grow.
    if hasattr(mx, "list_panes"):
        surfaces_after = {p["ref"] for p in mx.list_panes()}
        assert len(surfaces_after) <= len(surfaces_before) or surfaces_before == set(), (
            f"respawn leaked an orphan surface: before={surfaces_before} "
            f"after={surfaces_after}"
        )

    mx.close(surface_ref)
