# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E031-SMOKE-001-live-spawn-argv-config-driven-scoped-bash
# Acceptance: acc:spawn-agents:E031-SMOKE-001-live-spawn-argv-config-driven-scoped-bash
# WMBT: wmbt:spawn-agents:E031
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""E031-SMOKE-001 — built through the REAL deployed code path, a claude-family
worker launch command carries the scoped Bash freedom set sourced from the live
session.convention.yaml, and none of the live forbidden commands.

SMOKE: imports the installed spawn.py + convention (no synthetic freedom_layer
fixture) and exercises the actual adapter assembly end-to-end.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import pytest
import yaml


@pytest.mark.smoke
def test_live_adapter_command_carries_config_driven_scoped_bash(tmp_path: Path):
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY
    import atdd.coach.commands.spawn as spawn

    convention = (
        Path(spawn.__file__).resolve().parent.parent
        / "conventions"
        / "session.convention.yaml"
    )
    fl = yaml.safe_load(convention.read_text(encoding="utf-8"))["spawn_time"][
        "freedom_layer"
    ]

    prompt_path = tmp_path / "launch-prompt.md"
    prompt_path.write_text("# launch prompt\n", encoding="utf-8")
    command = ADAPTER_REGISTRY["claude-code"].build_command(prompt_path)

    tokens = shlex.split(command)
    assert "--allowedTools" in tokens, (
        f"live claude-code adapter emits no --allowedTools: {command!r}"
    )
    # Comma-delimited so scoped multi-word Bash patterns survive as single entries.
    emitted = tokens[tokens.index("--allowedTools") + 1].split(",")

    for entry in ("Bash(pytest:*)", "Bash(atdd validate:*)"):
        assert entry in emitted, (
            f"E031-SMOKE-001: live --allowedTools must carry {entry!r} sourced from "
            f"the deployed convention — got {emitted!r}"
        )

    inner = [
        e[len("Bash(") : -len(":*)")]
        for e in emitted
        if e.startswith("Bash(") and e.endswith(":*)")
    ]
    for cmd in inner:
        for bad in fl.get("forbidden_bash") or []:
            assert not (cmd == bad or cmd.startswith(bad + " ")), (
                f"E031-SMOKE-001: live forbidden command {bad!r} leaked into the "
                f"emitted allowlist as 'Bash({cmd}:*)'"
            )
