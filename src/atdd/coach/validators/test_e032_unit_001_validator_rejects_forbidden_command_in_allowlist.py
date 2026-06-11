# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E032-UNIT-001-validator-rejects-forbidden-command-in-allowlist
# Acceptance: acc:spawn-agents:E032-UNIT-001-validator-rejects-forbidden-command-in-allowlist
# WMBT: wmbt:spawn-agents:E032
# Phase: GREEN
# Assertion: behavioral
"""E032-UNIT-001 — the flipped freedom-set validator fails when allowed_bash
contains a command that also appears in forbidden_bash, naming the offending entry.

RED: ``check_freedom_layer_allowlist_safety`` does not exist yet (the E013-era
check asserts 'Bash absent'). GREEN: the data-only validator flags any allowed_bash
entry whose inner command is listed in forbidden_bash.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.coder]


_FORBIDDEN = ["git push", "git commit", "git add", "rm", "mv", "cp", "gh", "pip", "sudo"]


def _validator():
    from atdd.coach.validators.freedom_layer_validator import (
        check_freedom_layer_allowlist_safety,
    )

    return check_freedom_layer_allowlist_safety


def test_forbidden_command_in_allowed_bash_yields_violation():
    check = _validator()
    tampered = {
        "allowed_tools": ["Read", "Edit"],
        "allowed_bash": ["Bash(pytest:*)", "Bash(git push:*)"],
        "forbidden_bash": _FORBIDDEN,
    }
    violations = check(tampered)
    assert violations, (
        "E032: validator must return at least one violation when a forbidden "
        "command ('git push') appears in allowed_bash"
    )
    assert any("git push" in v for v in violations), (
        f"E032: a violation must name the offending entry 'git push' — got {violations!r}"
    )


def test_clean_allowlist_yields_zero_violations():
    check = _validator()
    clean = {
        "allowed_tools": ["Read", "Edit", "Write"],
        "allowed_bash": ["Bash(pytest:*)", "Bash(atdd validate:*)", "Bash(grep:*)"],
        "forbidden_bash": _FORBIDDEN,
    }
    violations = check(clean)
    assert violations == [], (
        f"E032: a clean freedom_layer must yield zero violations — got {violations!r}"
    )
