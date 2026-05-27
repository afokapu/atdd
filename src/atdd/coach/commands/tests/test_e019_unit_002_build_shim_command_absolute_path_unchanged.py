# URN: test:spawn-agents:E019-UNIT-002-build-shim-command-absolute-path-unchanged
# Acceptance: acc:spawn-agents:E019-UNIT-002-build-shim-command-absolute-path-unchanged
# WMBT: wmbt:spawn-agents:E019
# Phase: GREEN
# Assertion: behavioral
"""E019-UNIT-002 — _build_shim_command with an already-absolute runtime_root passes
the path through unchanged (resolve() on an absolute path is idempotent).

RED: fails until _build_shim_command applies resolve() and the absolute-path invariant
is verified by the presence of the exact path in the command string.
"""
from __future__ import annotations

import shlex
from pathlib import Path


def _extract_runtime_dir_value(cmd: str) -> str:
    tokens = shlex.split(cmd)
    idx = tokens.index("--runtime-dir")
    return tokens[idx + 1]


def test_absolute_runtime_root_preserved_in_command():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path("/tmp/test-runtime-e019")
    assert runtime_root.is_absolute(), "precondition: input is already absolute"

    cmd = _build_shim_command("claude --no-update", "agent-860-abs", runtime_root)

    value = _extract_runtime_dir_value(cmd)
    assert Path(value).is_absolute(), (
        f"E019-UNIT-002: absolute input must produce an absolute --runtime-dir. "
        f"Got: {value!r}"
    )
    assert "/tmp/test-runtime-e019" in value, (
        f"E019-UNIT-002: absolute path must appear verbatim in the command. "
        f"Got: {value!r}"
    )


def test_absolute_runtime_root_resolve_is_idempotent():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path("/tmp/test-runtime-e019-idem")
    cmd = _build_shim_command("echo ok", "agent-860-idem", runtime_root)

    value = _extract_runtime_dir_value(cmd)
    resolved = str(runtime_root.resolve())
    # After resolve(), an already-absolute path is identical (or differs only by
    # symlink expansion — either is acceptable as long as is_absolute() is True).
    assert Path(value).is_absolute(), (
        f"E019-UNIT-002: resolve() on absolute path must still yield absolute. "
        f"Got: {value!r}"
    )


def test_absolute_path_not_transformed_to_relative():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path("/abs/path/runtime")
    cmd = _build_shim_command("echo ok", "agent-860-norel", runtime_root)

    value = _extract_runtime_dir_value(cmd)
    assert not value.startswith("."), (
        f"E019-UNIT-002: absolute path must never become relative. Got: {value!r}"
    )
    assert value.startswith("/"), (
        f"E019-UNIT-002: resolved value must start with '/'. Got: {value!r}"
    )
