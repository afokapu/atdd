# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E031-UNIT-002-spawn-emits-convention-sourced-scoped-allowlist
# Acceptance: acc:spawn-agents:E031-UNIT-002-spawn-emits-convention-sourced-scoped-allowlist
# WMBT: wmbt:spawn-agents:E031
# Phase: GREEN
# Assertion: behavioral
"""E031-UNIT-002 — the claude-family adapter in spawn.py emits --allowedTools
SOURCED from the convention freedom_layer (allowed_tools ∪ allowed_bash), not from
a hardcoded module literal.

RED: today ``_claude_code_adapter`` emits the hardcoded ``_CLAUDE_ALLOWED_TOOLS``
image (Read Edit Write TodoWrite Glob Grep WebFetch, Bash deliberately absent), so
``Bash(pytest:*)`` never appears and the emitted set does not match the convention
data. The coder makes the adapter read ``allowed_tools ∪ allowed_bash`` from
session.convention.yaml::spawn_time.freedom_layer.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.coder]


def _freedom_layer() -> dict:
    import atdd.coach.commands.spawn as spawn

    convention = (
        Path(spawn.__file__).resolve().parent.parent
        / "conventions"
        / "session.convention.yaml"
    )
    data = yaml.safe_load(convention.read_text(encoding="utf-8"))
    return data["spawn_time"]["freedom_layer"]


def _emitted_allowed_tools(tmp_path: Path) -> list[str]:
    """Build the live claude-code adapter command and parse the --allowedTools value."""
    from atdd.coach.commands.spawn import ADAPTER_REGISTRY

    prompt_path = tmp_path / "launch-prompt.md"
    prompt_path.write_text("# launch prompt\n", encoding="utf-8")
    command = ADAPTER_REGISTRY["claude-code"].build_command(prompt_path)

    tokens = shlex.split(command)
    assert "--allowedTools" in tokens, (
        f"claude-code adapter command emits no --allowedTools flag: {command!r}"
    )
    value = tokens[tokens.index("--allowedTools") + 1]
    # Comma-delimited so scoped multi-word Bash patterns (e.g. ``Bash(atdd
    # validate:*)``) survive as single entries — Claude Code's --allowedTools format.
    return value.split(",")


def test_emitted_allowlist_contains_every_convention_entry(tmp_path: Path):
    fl = _freedom_layer()
    expected = list(fl.get("allowed_tools") or []) + list(fl.get("allowed_bash") or [])
    assert expected, (
        "E031: convention freedom_layer must declare allowed_tools/allowed_bash"
    )

    emitted = _emitted_allowed_tools(tmp_path)
    missing = [entry for entry in expected if entry not in emitted]
    assert not missing, (
        "E031: claude-code adapter --allowedTools is not sourced from the convention "
        f"freedom_layer — missing entries {missing!r}; emitted {emitted!r}"
    )


def test_scoped_bash_pytest_entry_is_present(tmp_path: Path):
    emitted = _emitted_allowed_tools(tmp_path)
    assert "Bash(pytest:*)" in emitted, (
        "E031: the emitted --allowedTools must carry the scoped safe entry "
        f"'Bash(pytest:*)' from the convention — got {emitted!r}"
    )


def test_no_forbidden_command_appears_in_emitted_allowlist(tmp_path: Path):
    fl = _freedom_layer()
    forbidden = list(fl.get("forbidden_bash") or [])
    assert forbidden, "E031: convention must declare forbidden_bash"

    emitted = _emitted_allowed_tools(tmp_path)
    # Each Bash entry is Bash(<cmd>:*); a forbidden command must never be the
    # inner command of an emitted entry (prefix-match injection guard).
    inner_cmds = [
        e[len("Bash(") : -len(":*)")]
        for e in emitted
        if e.startswith("Bash(") and e.endswith(":*)")
    ]
    for cmd in inner_cmds:
        for bad in forbidden:
            assert not (cmd == bad or cmd.startswith(bad + " ")), (
                f"E031: forbidden command {bad!r} leaked into the emitted allowlist "
                f"as scoped entry 'Bash({cmd}:*)'"
            )


def test_emitted_allowlist_matches_convention_union_exactly(tmp_path: Path):
    """The emitted set is the image of the convention data — proving it is read
    from the convention, not assembled from an independent hardcoded literal."""
    fl = _freedom_layer()
    expected = set(fl.get("allowed_tools") or []) | set(fl.get("allowed_bash") or [])
    emitted = set(_emitted_allowed_tools(tmp_path))
    assert emitted == expected, (
        "E031: emitted --allowedTools set must equal allowed_tools ∪ allowed_bash "
        f"from the convention.\n  emitted:  {sorted(emitted)}\n  expected: {sorted(expected)}"
    )
