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
carry NO such flag, and must leave the BROAD Bash class OUT of --allowedTools so an
unscoped Bash decision raises a PermissionRequest the hook can publish. Scoped safe
prefixes (``Bash(<cmd>:*)``, the config-driven freedom set — E031 #1062) MAY be
pre-authorized; only bare ``Bash`` / ``Bash(*)`` / ``Bash(:*)`` are forbidden. This
locks the regression the own-workspace hypothesis (now reverted) failed to address.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from atdd.coach.commands import spawn

# A tightly-scoped Bash entry: Bash(<cmd>:*). Bare Bash / Bash(*) / Bash(:*) fail.
_SCOPED_BASH_RE = re.compile(r"^Bash\([^()]+:\*\)$")

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


def test_dispatch_launch_leaves_broad_bash_unallowed(tmp_path: Path):
    command = _dispatch_launch_command(tmp_path)
    tokens = shlex.split(command)
    assert "--allowedTools" in tokens, command
    # Comma-delimited freedom set; scoped multi-word Bash patterns survive intact.
    entries = tokens[tokens.index("--allowedTools") + 1].split(",")
    bash_entries = [e for e in entries if e == "Bash" or e.startswith("Bash(")]
    # The broad Bash class (bare Bash / Bash(*) / Bash(:*)) must NOT be
    # pre-authorized — it must raise a PermissionRequest the wrapper hook publishes
    # to the Feed. Only tightly-scoped Bash(<cmd>:*) safe prefixes may auto-run.
    for entry in bash_entries:
        assert _SCOPED_BASH_RE.match(entry), (
            f"over-broad/bare Bash entry {entry!r} pre-authorized at launch — only "
            f"scoped Bash(<cmd>:*) may auto-run; the broad class must surface (#1062)\n"
            f"{command}"
        )
