# URN: test:spawn-agents:E019-SMOKE-001-shim-command-runtime-dir-is-absolute-in-live-spawn
# Acceptance: acc:spawn-agents:E019-SMOKE-001-shim-command-runtime-dir-is-absolute-in-live-spawn
# WMBT: wmbt:spawn-agents:E019
# Phase: SMOKE
# Layer: backend.smoke
# Runtime: python
# Assertion: behavioral
"""E019-SMOKE-001 — against the deployed (installed) atdd package, _build_shim_command
always produces a --runtime-dir value that is an absolute path when given a relative input.

Smoke gate: requires ATDD_RUN_SMOKE=1.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E019-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_build_shim_command_resolves_relative_runtime_dir():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path(".atdd/runtime")
    assert not runtime_root.is_absolute(), "precondition: input is relative"

    cmd = _build_shim_command("claude --no-update", "smoke-agent-e019", runtime_root)

    tokens = shlex.split(cmd)
    idx = tokens.index("--runtime-dir")
    value = tokens[idx + 1]

    assert Path(value).is_absolute(), (
        f"E019-SMOKE-001: deployed _build_shim_command must produce an absolute --runtime-dir. "
        f"Got: {value!r}"
    )


@pytest.mark.skipif(
    not os.environ.get("ATDD_RUN_SMOKE"),
    reason="E019-SMOKE-001 requires ATDD_RUN_SMOKE=1",
)
def test_deployed_build_shim_command_absolute_input_unchanged():
    from atdd.coach.commands.spawn import _build_shim_command

    runtime_root = Path("/tmp/smoke-e019-abs-runtime")
    cmd = _build_shim_command("claude --no-update", "smoke-agent-e019-abs", runtime_root)

    tokens = shlex.split(cmd)
    idx = tokens.index("--runtime-dir")
    value = tokens[idx + 1]

    assert Path(value).is_absolute(), (
        f"E019-SMOKE-001: absolute input must remain absolute after resolve(). Got: {value!r}"
    )
