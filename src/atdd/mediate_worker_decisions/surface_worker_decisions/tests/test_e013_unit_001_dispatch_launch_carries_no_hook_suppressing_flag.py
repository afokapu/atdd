# URN: test:mediate-worker-decisions:surface-worker-decisions:E013-UNIT-001-dispatch-launch-carries-no-hook-suppressing-flag
# Acceptance: acc:mediate-worker-decisions:E013-UNIT-001-dispatch-launch-carries-no-hook-suppressing-flag
# WMBT: wmbt:mediate-worker-decisions:E013
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E013-UNIT-001 — the dispatch worker launch carries no hook-suppressing flag.

The cmux claude wrapper injects the PermissionRequest->'cmux hooks feed' hook
ONLY when the invocation is a clean session entrypoint: passing ``--settings``
(overrides the wrapper's hook settings), ``-p``/``--print`` or ``-r``/``--resume``
suppresses it (coach live-repro on 3.110.0: a dispatch worker's Bash permission
hit the TUI, feed.list empty). The dispatch-built worker launch must therefore
carry NO such flag, and must leave Bash OUT of --allowedTools so a Bash decision
raises a PermissionRequest the hook can publish. This locks the regression the
own-workspace hypothesis (now reverted) failed to address.
"""
from __future__ import annotations

import shlex
from pathlib import Path

from atdd.coach.commands import spawn

# Flags that suppress the cmux wrapper's Feed-hook injection (per the wrapper).
_SUPPRESSING_FLAGS = {
    "--settings", "-p", "--print", "-r", "--resume", "-c", "--continue",
}


def _dispatch_launch_command(tmp_path: Path) -> str:
    """The exact worker launch command the cmux-native dispatch builds."""
    prompt_path = tmp_path / ".launch_prompt.txt"
    prompt_path.write_text("Do the ATDD task: run atdd gate then proceed.")
    adapter_cmd = spawn.ADAPTER_REGISTRY["claude-code"](prompt_path)
    return spawn._build_cmux_native_command(adapter_cmd, prompt_path.read_text())


def test_dispatch_launch_has_no_hook_suppressing_flag(tmp_path: Path):
    tokens = shlex.split(_dispatch_launch_command(tmp_path))
    suppressors = [t for t in tokens if t in _SUPPRESSING_FLAGS]
    assert suppressors == [], (
        f"dispatch worker launch carries hook-suppressing flag(s) {suppressors} — "
        f"the cmux wrapper will not inject the Feed hook, so the worker hangs "
        f"unmediated on its first decision (TUI modal, empty feed.list)"
    )


def test_dispatch_launch_leaves_bash_unallowed(tmp_path: Path):
    command = _dispatch_launch_command(tmp_path)
    _, _, after_allowed = command.partition("--allowedTools")
    # Bash must NOT be pre-authorized — it must raise a PermissionRequest the
    # wrapper hook publishes to the Feed for the daemon to mediate.
    assert "Bash" not in after_allowed, command
