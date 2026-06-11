# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E031-UNIT-001-convention-declares-freedom-layer-data
# Acceptance: acc:spawn-agents:E031-UNIT-001-convention-declares-freedom-layer-data
# WMBT: wmbt:spawn-agents:E031
# Phase: GREEN
# Assertion: behavioral
"""E031-UNIT-001 — session.convention.yaml::spawn_time.freedom_layer declares the
freedom set as DATA (allowed_tools, allowed_bash, forbidden_bash), not prose.

RED: today freedom_layer carries prose + a ``claude_flags`` literal but none of the
three data lists. The coder makes the convention the source of truth by declaring
``allowed_tools`` / ``allowed_bash`` / ``forbidden_bash`` as non-empty string lists.
"""
from __future__ import annotations

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


def _is_str_list(value) -> bool:
    return isinstance(value, list) and len(value) > 0 and all(
        isinstance(item, str) for item in value
    )


def test_allowed_tools_is_non_empty_str_list_with_expected_members():
    fl = _freedom_layer()
    allowed_tools = fl.get("allowed_tools")
    assert _is_str_list(allowed_tools), (
        "E031: spawn_time.freedom_layer.allowed_tools must be a non-empty list of "
        f"strings — got {allowed_tools!r}"
    )
    for tool in ("Read", "Edit", "Write", "TodoWrite", "Glob", "Grep", "WebFetch"):
        assert tool in allowed_tools, (
            f"E031: allowed_tools must include the auto-allow tool {tool!r}"
        )


def test_allowed_bash_is_non_empty_str_list_with_scoped_entries():
    fl = _freedom_layer()
    allowed_bash = fl.get("allowed_bash")
    assert _is_str_list(allowed_bash), (
        "E031: spawn_time.freedom_layer.allowed_bash must be a non-empty list of "
        f"strings — got {allowed_bash!r}"
    )
    for entry in ("Bash(pytest:*)", "Bash(atdd validate:*)"):
        assert entry in allowed_bash, (
            f"E031: allowed_bash must include the scoped safe entry {entry!r}"
        )


def test_forbidden_bash_is_non_empty_str_list_with_destructive_members():
    fl = _freedom_layer()
    forbidden_bash = fl.get("forbidden_bash")
    assert _is_str_list(forbidden_bash), (
        "E031: spawn_time.freedom_layer.forbidden_bash must be a non-empty list of "
        f"strings — got {forbidden_bash!r}"
    )
    for cmd in ("git push", "git commit", "rm", "gh", "sudo"):
        assert cmd in forbidden_bash, (
            f"E031: forbidden_bash must list the destructive/outward command {cmd!r}"
        )
