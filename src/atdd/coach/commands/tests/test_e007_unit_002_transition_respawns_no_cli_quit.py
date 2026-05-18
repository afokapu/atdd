# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E007-UNIT-002-transition-respawns-no-cli-specific-quit
# Acceptance: acc:spawn-agents:E007-UNIT-002-transition-respawns-no-cli-specific-quit
# WMBT: wmbt:spawn-agents:E007
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E007-UNIT-002 — on a phase transition the coach recycles the worker process
via the multiplexer abstraction's respawn primitive, never a hardcoded
CLI-specific quit (``/exit``, ``/quit``, ``/clear``).

RED: the terminate must be CLI-agnostic and uniform across backends. Today
``TmuxBackend`` and ``ZellijBackend`` do not implement ``respawn_pane`` — they
inherit the ``MultiplexerBackend`` base stub that raises ``NotImplementedError``
— so the coach's kill+relaunch is not actually backend-neutral. This test pins
that every concrete backend exposes the respawn primitive and that the
transition path carries no CLI-specific quit literal.
"""
from __future__ import annotations

from pathlib import Path

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

_CLI_QUIT_LITERALS = ("/exit", "/quit", "/clear")


def test_transition_recycles_worker_via_respawn_primitive(tmp_path, monkeypatch):
    """A phase transition issues an in-place respawn against the issue's
    surface and sends no CLI-specific quit string."""
    fake_mx = FakeRespawnMx()
    spawn_handler = patch_spawn_env(tmp_path, monkeypatch, fake_mx)
    ctx = CoachContext(issue_number=746, multiplexer_mode="pane")

    r1 = spawn_handler.handle(ctx, Transition(src=Phase.INIT, dst=Phase.PLANNED))
    assert r1 == HandlerResult.HANDLED
    assert fake_mx.panes, "first phase created no surface"
    surface_ref = next(iter(fake_mx.panes))

    r2 = spawn_handler.handle(ctx, Transition(src=Phase.PLANNED, dst=Phase.RED))
    assert r2 == HandlerResult.HANDLED

    respawns = fake_mx.ops("respawn")
    assert respawns, (
        "the phase transition issued no respawn — the worker process was not "
        "recycled for the next phase"
    )
    assert any(c["ref"] == surface_ref for c in respawns), (
        f"respawn did not target the issue's surface {surface_ref}: {respawns}"
    )

    for text in fake_mx.texts_sent():
        for literal in _CLI_QUIT_LITERALS:
            assert literal not in text, (
                f"a CLI-specific quit {literal!r} was sent to the worker "
                f"surface: {text!r}"
            )


def test_no_cli_specific_quit_literal_in_spawn_path():
    """The coach spawn/transition source carries no hardcoded CLI-specific
    quit literal — the terminate is the multiplexer respawn primitive."""
    from atdd.coach.commands import spawn as cmd_spawn_mod
    from atdd.coach.handlers import spawn as spawn_handler

    for module in (cmd_spawn_mod, spawn_handler):
        src = Path(module.__file__).read_text()
        # strip the test-literal tuple this very test family references
        for literal in ("/exit", "/quit"):
            assert literal not in src, (
                f"{module.__name__} hardcodes a CLI-specific quit {literal!r} "
                f"— the terminate must be the multiplexer respawn primitive"
            )


def test_every_concrete_backend_implements_respawn_primitive():
    """cmux, tmux and zellij each override the respawn primitive — none falls
    through to the base-class ``NotImplementedError`` stub."""
    from atdd.coach.utils.multiplexer import (
        CmuxBackend,
        MultiplexerBackend,
        TmuxBackend,
        ZellijBackend,
    )

    base = MultiplexerBackend.respawn_pane
    for backend_cls in (CmuxBackend, TmuxBackend, ZellijBackend):
        assert backend_cls.respawn_pane is not base, (
            f"{backend_cls.__name__} does not override respawn_pane — it "
            f"inherits the base stub that raises NotImplementedError, so the "
            f"coach cannot recycle the worker process on this backend"
        )
