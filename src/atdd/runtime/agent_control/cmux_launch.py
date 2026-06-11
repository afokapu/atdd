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
import shutil
from pathlib import Path
from typing import Sequence

# Top-level ~/.claude entries that MUST NOT be carried into a worker's isolated
# config dir (#1066, E030): ``projects/`` holds the auto-memory + session
# transcripts that #1057 isolates (seeding it would reintroduce the bleed), and
# ``history.jsonl`` is large + operator-private. Everything else (auth,
# onboarding markers, settings, caches) is what lets a worker authenticate and
# skip first-run onboarding instead of parking on the login screen.
_SEED_EXCLUDE: frozenset[str] = frozenset({"projects", "history.jsonl"})


def operator_config_root() -> Path:
    """The operator's Claude config root (``~/.claude``) — the seed SOURCE.

    This is the authenticated, onboarded config a spawned worker must inherit
    from (minus ``projects/``) so it can run non-interactively (#1066).
    """
    return Path.home() / ".claude"


def seed_plan(config_root: Path) -> list[str]:
    """Pure derivation of the seed-plan for the isolated ``CLAUDE_CONFIG_DIR``
    (#1066, E030-UNIT-004).

    Given the operator config root, returns the sorted set of top-level entry
    names to carry into the isolated dir = every entry EXCEPT ``projects/`` and
    ``history.jsonl``. Deterministic and side-effect free (it only reads the
    directory listing); returns ``[]`` when the root is absent.
    """
    root = Path(config_root)
    if not root.is_dir():
        return []
    return sorted(
        entry.name for entry in root.iterdir() if entry.name not in _SEED_EXCLUDE
    )


def seed_isolated_config_dir(config_dir: Path, config_root: Path | None = None) -> Path:
    """Seed a worker's isolated ``CLAUDE_CONFIG_DIR`` with the operator's
    non-memory config so the worker can authenticate + skip onboarding (#1066,
    E030-UNIT-005).

    Carries every ``seed_plan`` entry from ``config_root`` (default
    ``operator_config_root()``) into ``config_dir`` — top-level FILES are copied
    (so worker writes don't mutate operator state), top-level DIRS are symlinked
    (cheap; they are heavy + read-mostly, e.g. plugins/statsig). ``projects/`` is
    never carried, so worker memory + transcripts still start fresh in the
    isolated dir (the #1057 guarantee holds). Idempotent: pre-existing entries
    are left untouched, and a single unreadable entry never aborts the launch.
    """
    config_dir = Path(config_dir)
    root = Path(config_root) if config_root is not None else operator_config_root()
    config_dir.mkdir(parents=True, exist_ok=True)
    for name in seed_plan(root):
        src = root / name
        dst = config_dir / name
        if dst.exists() or dst.is_symlink():
            continue  # idempotent — never duplicate or overwrite an existing entry
        try:
            if src.is_dir():
                dst.symlink_to(src)
            else:
                shutil.copy2(src, dst)
        except OSError:
            # Best-effort seed: a single unreadable/odd entry must not block the
            # worker launch. The worker degrades to the (pre-#1066) behavior for
            # that one entry only.
            continue
    return config_dir


def isolated_claude_config_dir(agent_id: str, worktree_root: Path) -> Path:
    """Derive the per-worker isolated ``CLAUDE_CONFIG_DIR`` path (#1057, E030).

    This is the ONE source of truth both launch planes consume — the cmux-native
    surface env (``build_worker_launch_env``) and the legacy/headless adapter
    (``spawn.py::_inject_agent_env``). It returns a path UNDER the issue worktree's
    ``.atdd/runtime`` subtree, keyed by ``agent_id`` so distinct workers never
    collide, and NEVER under the operator's ``~/.claude`` config dir.

    Relocating Claude Code's config/memory/projects root here stops worker
    auto-memory from bleeding back into the operator's shared ``-main`` memory dir
    (auto-memory keys off the git-common-dir, which every linked worktree shares).
    """
    return (
        Path(worktree_root)
        / ".atdd"
        / "runtime"
        / "agents"
        / agent_id
        / "claude-home"
    )


def build_worker_launch_env(
    agent_id: str, worktree_root: Path, *, config_root: Path | None = None
) -> dict[str, str]:
    """Build the cmux-native worker launch env carrying the isolated, SEEDED
    ``CLAUDE_CONFIG_DIR`` (#1057 isolation + #1066 seed).

    The value is the single-source-of-truth ``isolated_claude_config_dir``
    derivation, and the dir is SEEDED before the env is emitted (#1066,
    E030-UNIT-006) so the worker inherits the operator's auth/onboarding/settings
    (everything except ``projects/``) and never launches against an empty,
    auth-less config dir. ``config_root`` is injectable for tests; production
    leaves it ``None`` → the real ``~/.claude``. No Feed-disabling lever is
    smuggled in here — ``--bare`` / ``CLAUDE_CODE_SIMPLE`` are explicitly rejected
    (Decision #2) so the cmux wrapper's Feed-publishing hooks stay active.
    """
    config_dir = isolated_claude_config_dir(agent_id, worktree_root)
    seed_isolated_config_dir(config_dir, config_root)
    return {"CLAUDE_CONFIG_DIR": str(config_dir)}


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
