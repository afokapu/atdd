"""Pure builders for the cmux-native worker launch (#978).

The shim launch transport is replaced: instead of a pty-owning shim that injects
and submits the prompt, cmux opens a surface running the agent directly and the
agent's **positional prompt** seeds (and auto-submits) the first turn. There is no
pty, no ``cli-return.jsonl`` inbox, and no submit sentinel — decision
communication rides the cmux Feed (the wrapper's ``PermissionRequest``/
``AskUserQuestion`` hooks), not this layer.

Verified live (2026-06-05 spike): ``cmux new-workspace --command 'claude "<brief>"
…'`` boots the agent and the positional prompt both lands AND auto-submits. The one
ordering rule: the prompt MUST precede ``--allowedTools`` (which is variadic and
would otherwise swallow the trailing positional).

Stdlib only (§3.3) and pure, so the launch shape is unit-testable without a real
cmux.
"""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Sequence


def build_agent_seed_argv(
    agent_bin: str,
    prompt: str,
    *,
    permission_mode: str,
    allowed_tools: Sequence[str] = (),
) -> list[str]:
    """Build the agent argv that seeds the first turn via the POSITIONAL prompt.

    Ordering is load-bearing: the prompt comes first because ``--allowedTools`` is
    variadic and would consume a trailing positional (the empty-prompt failure
    observed in the 2026-06-05 spike). An empty ``allowed_tools`` omits the flag
    entirely so no dangling empty value is emitted.

    The agent binary is launched under the cmux wrapper (resolved via PATH inside
    the surface), so ``CMUX_SURFACE_ID`` is set and the Feed hooks are injected —
    this builder never adds a permission-bypass flag.
    """
    argv: list[str] = [agent_bin, prompt, "--permission-mode", permission_mode]
    if allowed_tools:
        argv += ["--allowedTools", " ".join(allowed_tools)]
    return argv


def build_cmux_launch_argv(
    agent_argv: Sequence[str],
    *,
    cwd: Path,
    name: str,
    cmux_bin: str = "cmux",
) -> list[str]:
    """Build the ``cmux new-workspace`` argv that runs ``agent_argv`` in a surface.

    The agent command is passed as a single ``--command`` shell string (shlex-quoted
    so the positional prompt and the space-joined ``--allowedTools`` value survive as
    single tokens). The surface ``--cwd`` is the worktree, so ``CMUX_SURFACE_ID`` is
    set there and the cmux wrapper injects the Feed-publishing hooks.
    """
    command_str = shlex.join(agent_argv)
    return [
        cmux_bin,
        "new-workspace",
        "--name",
        name,
        "--cwd",
        str(Path(cwd).resolve()),
        "--command",
        command_str,
    ]
