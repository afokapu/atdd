# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E031-UNIT-003-cmux-launch-argv-carries-scoped-bash-allowlist
# Acceptance: acc:spawn-agents:E031-UNIT-003-cmux-launch-argv-carries-scoped-bash-allowlist
# WMBT: wmbt:spawn-agents:E031
# Phase: GREEN
# Assertion: behavioral
"""E031-UNIT-003 — the cmux-native launch plane carries the convention-sourced
scoped Bash allow-list, with the load-bearing prompt-before-flags ordering preserved.

RED: the convention does not yet declare ``allowed_bash``, so the resolved
allow-list carries no ``Bash(pytest:*)`` / ``Bash(atdd validate:*)`` entries and the
argv assertion fails. GREEN: freedom_layer declares the scoped data and the resolved
allow-list passed to ``build_agent_seed_argv`` carries it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.coder]

from atdd.runtime.agent_control.cmux_launch import build_agent_seed_argv


def _convention_sourced_allowlist() -> list[str]:
    import atdd.coach.commands.spawn as spawn

    convention = (
        Path(spawn.__file__).resolve().parent.parent
        / "conventions"
        / "session.convention.yaml"
    )
    fl = yaml.safe_load(convention.read_text(encoding="utf-8"))["spawn_time"][
        "freedom_layer"
    ]
    return list(fl.get("allowed_tools") or []) + list(fl.get("allowed_bash") or [])


def _allowed_tools_value(argv: list[str]) -> str:
    assert "--allowedTools" in argv, (
        f"argv carries no --allowedTools flag: {argv!r}"
    )
    return argv[argv.index("--allowedTools") + 1]


def test_argv_carries_scoped_bash_entries():
    prompt = "seed the first turn"
    argv = build_agent_seed_argv(
        "claude",
        prompt,
        permission_mode="acceptEdits",
        allowed_tools=_convention_sourced_allowlist(),
    )
    value = _allowed_tools_value(argv)
    for entry in ("Bash(pytest:*)", "Bash(atdd validate:*)"):
        assert entry in value, (
            f"E031: cmux launch --allowedTools must carry {entry!r} — got {value!r}"
        )


def test_positional_prompt_precedes_allowed_tools():
    prompt = "seed the first turn"
    argv = build_agent_seed_argv(
        "claude",
        prompt,
        permission_mode="acceptEdits",
        allowed_tools=_convention_sourced_allowlist(),
    )
    assert prompt in argv, "positional prompt missing from argv"
    assert argv.index(prompt) < argv.index("--allowedTools"), (
        "E031: the positional prompt MUST precede --allowedTools (variadic flag would "
        f"otherwise swallow the prompt) — argv {argv!r}"
    )


def test_no_forbidden_command_in_argv_allowed_tools():
    import atdd.coach.commands.spawn as spawn

    convention = (
        Path(spawn.__file__).resolve().parent.parent
        / "conventions"
        / "session.convention.yaml"
    )
    fl = yaml.safe_load(convention.read_text(encoding="utf-8"))["spawn_time"][
        "freedom_layer"
    ]
    forbidden = list(fl.get("forbidden_bash") or [])
    assert forbidden, "E031: convention must declare forbidden_bash"

    argv = build_agent_seed_argv(
        "claude",
        "seed",
        permission_mode="acceptEdits",
        allowed_tools=_convention_sourced_allowlist(),
    )
    value = _allowed_tools_value(argv)
    inner = [
        tok[len("Bash(") : -len(":*)")]
        for tok in value.split()
        if tok.startswith("Bash(") and tok.endswith(":*)")
    ]
    for cmd in inner:
        for bad in forbidden:
            assert not (cmd == bad or cmd.startswith(bad + " ")), (
                f"E031: forbidden command {bad!r} leaked into the cmux launch argv "
                f"as 'Bash({cmd}:*)'"
            )
