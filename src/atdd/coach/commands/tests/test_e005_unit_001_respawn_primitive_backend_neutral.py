# URN: test:spawn-agents:per-phase-fresh-agent-respawn:E005-UNIT-001-respawn-primitive-backend-neutral-same-surface
# Acceptance: acc:spawn-agents:E005-UNIT-001-respawn-primitive-backend-neutral-same-surface
# WMBT: wmbt:spawn-agents:E005
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E005-UNIT-001 — the multiplexer abstraction's respawn primitive kills the
current process and relaunches a fresh one in the SAME surface, on every
concrete backend (cmux, tmux, zellij).

RED: only ``CmuxBackend`` implements ``respawn_pane``. ``TmuxBackend`` and
``ZellijBackend`` inherit the ``MultiplexerBackend`` base, which raises
``NotImplementedError`` — so a phase transition on tmux/zellij silently leaves
the prior-phase process running instead of recycling it. This test pins an
in-place respawn on all three backends: a fresh process inside the existing
surface, never a fresh surface.
"""
from __future__ import annotations

from typing import Any

import pytest

from atdd.coach.utils import multiplexer as mx_mod
from atdd.coach.utils.multiplexer import CmuxBackend, TmuxBackend, ZellijBackend

pytestmark = [pytest.mark.platform]


_NEW_COMMAND = 'claude --permission-mode acceptEdits --allowedTools "Bash Edit"'


class _RunRecorder:
    """Records every backend subprocess argv without spawning real processes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd: Any, capture: bool = True):  # mimics multiplexer._run
        self.calls.append([str(tok) for tok in cmd])

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    def flat(self) -> list[str]:
        return [tok for cmd in self.calls for tok in cmd]


@pytest.mark.parametrize(
    "backend_cls", [CmuxBackend, TmuxBackend, ZellijBackend]
)
def test_respawn_primitive_backend_neutral_same_surface(backend_cls, monkeypatch):
    """Every concrete backend respawns in place — native verb, same ref, no
    new surface allocated, and no ``NotImplementedError``."""
    recorder = _RunRecorder()
    monkeypatch.setattr(mx_mod, "_run", recorder)

    backend = backend_cls()
    surface_ref = "surface:7"

    try:
        backend.respawn_pane(surface_ref, command=_NEW_COMMAND)
    except NotImplementedError as exc:  # noqa: PERF203 — the RED assertion
        pytest.fail(
            f"{backend.name} backend does not implement the respawn primitive: "
            f"{exc} — a phase transition on this backend cannot recycle the "
            f"worker process"
        )

    assert recorder.calls, (
        f"{backend.name} respawn_pane issued no backend command"
    )

    flat = recorder.flat()
    assert surface_ref in flat, (
        f"{backend.name} respawn did not reuse the supplied surface ref "
        f"{surface_ref!r}: {recorder.calls}"
    )

    joined = " ".join(flat)
    assert "respawn" in joined or "kill" in joined, (
        f"{backend.name} respawn issued no native in-place respawn/kill verb: "
        f"{recorder.calls}"
    )

    assert not any(
        tok in ("new-window", "new-session", "new-pane", "split-window")
        for tok in flat
    ), (
        f"{backend.name} respawn allocated a NEW surface instead of reusing "
        f"the existing one: {recorder.calls}"
    )
