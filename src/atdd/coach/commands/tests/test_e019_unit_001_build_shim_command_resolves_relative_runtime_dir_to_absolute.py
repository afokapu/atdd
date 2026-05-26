# URN: test:spawn-agents:E019-UNIT-001-build-shim-command-resolves-relative-runtime-dir-to-absolute
# Acceptance: acc:spawn-agents:E019-UNIT-001-build-shim-command-resolves-relative-runtime-dir-to-absolute
# WMBT: wmbt:spawn-agents:E019
# Phase: GREEN
# Assertion: behavioral
"""E019-UNIT-001 — _build_shim_command with a relative runtime_root resolves it to
an absolute path before embedding it as --runtime-dir in the command string.

RED: fails until _build_shim_command calls runtime_root.resolve() so the shim
always receives an absolute path regardless of the caller's CWD.
"""
from __future__ import annotations

import shlex
from pathlib import Path


def _extract_runtime_dir_value(cmd: str) -> str:
    tokens = shlex.split(cmd)
    idx = tokens.index("--runtime-dir")
    return tokens[idx + 1]


def test_relative_runtime_root_produces_absolute_runtime_dir_flag():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path(".atdd/runtime")
    assert not runtime_root.is_absolute(), "precondition: input is relative"

    cmd = _build_shim_command("claude --no-update", "agent-860-rel", runtime_root)

    value = _extract_runtime_dir_value(cmd)
    assert Path(value).is_absolute(), (
        f"E019-UNIT-001: --runtime-dir must be an absolute path when runtime_root is "
        f"relative. Got: {value!r} (not absolute). "
        "Fix: call runtime_root.resolve() inside _build_shim_command."
    )


def test_relative_runtime_root_does_not_start_with_dot():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path(".atdd/runtime")
    cmd = _build_shim_command("claude --no-update", "agent-860-dot", runtime_root)

    value = _extract_runtime_dir_value(cmd)
    assert not value.startswith("."), (
        f"E019-UNIT-001: --runtime-dir must not begin with '.' Got: {value!r}"
    )


def test_relative_runtime_root_with_subdir_segment_also_resolved():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path("out/runtime")
    cmd = _build_shim_command("echo ok", "agent-860-sub", runtime_root)

    value = _extract_runtime_dir_value(cmd)
    assert Path(value).is_absolute(), (
        f"E019-UNIT-001: any relative runtime_root variant must resolve to absolute. "
        f"Got: {value!r}"
    )
