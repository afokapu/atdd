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
surface, never a fresh workspace.
"""
from __future__ import annotations

from typing import Any

import pytest

from atdd.coach.utils import multiplexer as mx_mod
from atdd.coach.utils.multiplexer import CmuxBackend, TmuxBackend, ZellijBackend

pytestmark = [pytest.mark.platform]


_NEW_COMMAND = 'claude --permission-mode acceptEdits --allowedTools "Bash Edit"'
# Tokens that would indicate a genuinely NEW workspace/session was allocated
# rather than the existing surface being reused.
_NEW_WORKSPACE_TOKENS = ("new-session", "new-window", "new-workspace")


class _Recorder:
    """Records every backend subprocess invocation — argv + env — without
    spawning real processes. Stands in for both ``multiplexer._run`` and
    ``subprocess.run`` (zellij targets sessions via the env, not argv)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, *args: Any, **kwargs: Any):
        cmd = args[0] if args else (kwargs.get("args") or kwargs.get("cmd"))
        self.calls.append(
            {"argv": [str(tok) for tok in cmd],
             "env": dict(kwargs.get("env") or {})}
        )

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    def flat_argv(self) -> list[str]:
        return [tok for c in self.calls for tok in c["argv"]]

    def env_values(self) -> list[str]:
        return [v for c in self.calls for v in c["env"].values()]


@pytest.mark.parametrize(
    "backend_cls", [CmuxBackend, TmuxBackend, ZellijBackend]
)
def test_respawn_primitive_backend_neutral_same_surface(backend_cls, monkeypatch):
    """Every concrete backend respawns in place — reuses the surface ref,
    carries the replacement command, allocates no new workspace, and never
    raises ``NotImplementedError``."""
    recorder = _Recorder()
    monkeypatch.setattr(mx_mod, "_run", recorder)
    monkeypatch.setattr(mx_mod.subprocess, "run", recorder)

    backend = backend_cls()
    surface_ref = "surface:7"

    try:
        backend.respawn_pane(surface_ref, command=_NEW_COMMAND)
    except NotImplementedError as exc:
        pytest.fail(
            f"{backend.name} backend does not implement the respawn primitive: "
            f"{exc} — a phase transition on this backend cannot recycle the "
            f"worker process"
        )

    assert recorder.calls, (
        f"{backend.name} respawn_pane issued no backend command"
    )

    # The existing surface is reused — its ref appears in the argv (cmux/tmux)
    # or in the session-targeting env (zellij).
    flat = recorder.flat_argv()
    assert surface_ref in flat or surface_ref in recorder.env_values(), (
        f"{backend.name} respawn did not reuse the supplied surface ref "
        f"{surface_ref!r}: {recorder.calls}"
    )

    # The replacement launch command is what the fresh process runs.
    joined = " ".join(flat)
    assert _NEW_COMMAND in joined or _NEW_COMMAND in flat, (
        f"{backend.name} respawn did not carry the replacement launch "
        f"command: {recorder.calls}"
    )

    # No genuinely new workspace/session was allocated — the surface is reused.
    assert not any(tok in _NEW_WORKSPACE_TOKENS for tok in flat), (
        f"{backend.name} respawn allocated a new workspace instead of reusing "
        f"the existing surface: {recorder.calls}"
    )
