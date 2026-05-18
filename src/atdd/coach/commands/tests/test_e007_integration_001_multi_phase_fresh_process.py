# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E007-INTEGRATION-001-multi-phase-run-fresh-process-per-phase
# Acceptance: acc:spawn-agents:E007-INTEGRATION-001-multi-phase-run-fresh-process-per-phase
# WMBT: wmbt:spawn-agents:E007
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E007-INTEGRATION-001 — across a multi-phase run each phase respawns a FRESH
process in the SAME surface, and the surface name reflects the current phase.

This is issue #746's RED-first regression test. RED: the coach reuses one
surface per issue, but the surface keeps its ``ATDD<N>`` identity unchanged
across phases — there is no per-phase rename — so an operator cannot tell which
phase/agent is live. This test drives planner→tester→coder→tester→coder and
pins a fresh process per phase plus a phase-qualified name at every step.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.tests._e007_respawn_harness import (
    FakeRespawnMx,
    patch_spawn_env,
)
from atdd.coach.handlers.state_machine import (
    CoachContext,
    HandlerResult,
    Phase,
    Transition,
)

pytestmark = [pytest.mark.platform]

# (transition, destination-phase label expected in the surface name)
_RUN = [
    (Transition(src=Phase.INIT, dst=Phase.PLANNED), "PLANNED"),
    (Transition(src=Phase.PLANNED, dst=Phase.RED), "RED"),
    (Transition(src=Phase.RED, dst=Phase.GREEN), "GREEN"),
    (Transition(src=Phase.GREEN, dst=Phase.SMOKE), "SMOKE"),
    (Transition(src=Phase.SMOKE, dst=Phase.REFACTOR), "REFACTOR"),
]


def test_multi_phase_run_fresh_process_per_phase(tmp_path, monkeypatch):
    """A 5-phase run keeps one surface, runs a fresh process per phase, and
    names the surface for the live phase at every step."""
    fake_mx = FakeRespawnMx()
    spawn_handler = patch_spawn_env(tmp_path, monkeypatch, fake_mx)
    ctx = CoachContext(issue_number=746, multiplexer_mode="pane")

    for transition, _label in _RUN:
        assert spawn_handler.handle(ctx, transition) == HandlerResult.HANDLED, (
            f"transition {transition.src.value}->{transition.dst.value} "
            f"did not spawn"
        )

    # One surface for the whole lifecycle.
    assert len(fake_mx.panes) == 1, (
        f"the run created {len(fake_mx.panes)} surfaces — expected exactly one "
        f"persistent surface for the issue: {list(fake_mx.panes)}"
    )

    # A fresh process per phase — process identity changes at every transition.
    launches = fake_mx.spawn_or_respawn_calls()
    assert len(launches) == len(_RUN), (
        f"expected one launch per transition, got {len(launches)}"
    )
    processes = [c["process"] for c in launches]
    assert len(set(processes)) == len(processes), (
        f"a process identity was reused across phases — not a fresh process "
        f"per phase: {processes}"
    )

    # No carried-over conversation — a fresh process is started, not a reset.
    assert not any("/clear" in t for t in fake_mx.texts_sent()), (
        "a /clear conversation reset was sent — the worker process was not "
        "respawned fresh"
    )

    # The surface name reflects the live phase at every transition.
    rename_names = [c["name"] or "" for c in fake_mx.ops("rename")]
    for _transition, label in _RUN:
        assert any(label in name for name in rename_names), (
            f"no surface name reflected the {label} phase — the operator "
            f"cannot tell which phase is live. Renames: {rename_names}"
        )
