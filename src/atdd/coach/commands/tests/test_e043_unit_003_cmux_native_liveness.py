# URN: test:govern-lifecycle:cmux-native-worker-launcher:E043-UNIT-003-cmux-native-liveness-not-output-log-heartbeat
# Acceptance: acc:govern-lifecycle:E043-UNIT-003-cmux-native-liveness-not-output-log-heartbeat
# WMBT: wmbt:govern-lifecycle:E043
# Phase: GREEN
"""acc:govern-lifecycle:E043-UNIT-003 — on the cmux-native path worker liveness
derives from cmux surface state (``surface_to_pane``), NOT the 5s ``output.log``
heartbeat poll (which carried the cold-start flake). A vanished surface raises
``ProcessNotAlive`` so the coach escalates instead of proceeding with a dead
worker. The shim path's heartbeat is left untouched.
"""
from __future__ import annotations

from typing import Any

import pytest

from atdd.coach.commands.spawn import ProcessNotAlive, _verify_cmux_surface_alive

pytestmark = [pytest.mark.platform]


class _LiveBackend:
    """A backend whose surface maps to a live pane — and which would RAISE if
    anyone tried to read an output.log heartbeat off it (there is none)."""

    def __init__(self) -> None:
        self.probed: list[str] = []

    def surface_to_pane(self, surface_ref: str, workspace: Any = None) -> str:
        self.probed.append(surface_ref)
        return "pane:1"


class _DeadBackend:
    def surface_to_pane(self, surface_ref: str, workspace: Any = None) -> str:
        from atdd.coach.commands.spawn import MultiplexerError

        raise MultiplexerError(f"surface {surface_ref} not found in any pane")


class _BackendNoProbe:
    """No surface_to_pane — degrade gracefully (materialisation already guarded)."""


def test_live_surface_passes_via_cmux_state_no_output_log(tmp_path):
    backend = _LiveBackend()
    # No output.log anywhere — proof the check never depends on a heartbeat byte.
    _verify_cmux_surface_alive(backend, "surface:7", timeout_s=1.0)
    assert backend.probed == ["surface:7"]
    assert not (tmp_path / "output.log").exists()


def test_vanished_surface_raises_process_not_alive():
    with pytest.raises(ProcessNotAlive):
        _verify_cmux_surface_alive(_DeadBackend(), "surface:9", timeout_s=0.3,
                                   poll_interval_s=0.05)


def test_backend_without_probe_degrades_gracefully():
    # No probe primitive → no raise (surface_ref truthiness already guarded upstream).
    _verify_cmux_surface_alive(_BackendNoProbe(), "surface:1", timeout_s=0.3)
