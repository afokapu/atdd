# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E007-SMOKE-001-real-respawn-fresh-process-same-surface
# Acceptance: acc:spawn-agents:E007-SMOKE-001-real-respawn-fresh-process-same-surface
# WMBT: wmbt:spawn-agents:E007
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E007-SMOKE-001 — against a real multiplexer, the respawn primitive kills the
running process and a fresh process is observed in the same surface, leaving no
orphan.

Opt-in: skipped unless ``ATDD_RUN_SMOKE=1``. Coach multiplexer SMOKE tests are
opt-in because a clean multiplexer environment is not reliably available in CI
or inside an agent session — set ``ATDD_RUN_SMOKE=1`` to exercise it against
the locally installed multiplexer (cmux / tmux / zellij).
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
    """A real respawn on a real backend swaps the process in place: a fresh
    process runs in the same surface, and no orphan workspace is left behind."""
    from atdd.coach.utils.multiplexer import get_multiplexer

    mx = get_multiplexer()
    original = f"e005-original-{os.getpid()}"
    replacement = f"e005-replacement-{os.getpid()}"

    # A fresh, isolated workspace so the smoke run never touches the operator's
    # live sessions.
    workspace_ref = mx.new_workspace(
        cwd=os.getcwd(), command="true", name="ATDD746-e005-smoke",
    )
    surface_ref = None
    try:
        if mx.name == "cmux":
            # cmux: the surface is a distinct ref inside the workspace.
            surface_ref = mx.new_surface(
                workspace_ref=workspace_ref,
                command=f"sh -c 'echo {original}; sleep 600'",
                name="ATDD746-e005",
            )
        else:
            # tmux / zellij: the workspace ref IS the surface.
            surface_ref = workspace_ref
            mx.respawn_pane(
                surface_ref, command=f"sh -c 'echo {original}; sleep 600'",
            )
        time.sleep(2)

        # Respawn in place: kill the original process, relaunch a fresh one.
        mx.respawn_pane(
            surface_ref, command=f"sh -c 'echo {replacement}; sleep 600'",
        )
        time.sleep(3)

        if mx.name == "cmux":
            screen = mx.read_screen(surface_ref, lines=200, workspace=workspace_ref)
        else:
            screen = mx.read_screen(surface_ref, lines=200)
        assert replacement in screen, (
            "the fresh replacement process is not running in the surface after "
            f"respawn — screen: {screen!r}"
        )
    finally:
        # Clean up: no orphan workspace/surface left behind.
        if surface_ref is not None and mx.name == "cmux":
            try:
                mx.close(surface_ref, workspace=workspace_ref)
            except Exception:  # noqa: BLE001 — cleanup must not mask the result
                pass
        try:
            mx.close(workspace_ref)
        except Exception:  # noqa: BLE001 — cleanup must not mask the result
            pass
