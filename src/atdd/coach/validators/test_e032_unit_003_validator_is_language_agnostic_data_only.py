# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E032-UNIT-003-validator-is-language-agnostic-data-only
# Acceptance: acc:spawn-agents:E032-UNIT-003-validator-is-language-agnostic-data-only
# WMBT: wmbt:spawn-agents:E032
# Phase: GREEN
# Assertion: behavioral
"""E032-UNIT-003 — the validator operates purely on freedom_layer DATA (no
Python-specific code/AST inspection), so the same check holds for a non-Python
stack's allow-list (e.g. 'Bash(go test:*)', 'Bash(npm test:*)').

RED: the flipped data-only validator does not exist yet. GREEN: the check accepts a
plain dict and never imports or parses a Python source module, so the rule is
constant across stacks while the per-language data varies (#1035).
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


def test_non_python_stack_allowlist_passes():
    check = _validator()
    non_python = {
        "allowed_tools": ["Read", "Edit"],
        "allowed_bash": ["Bash(go test:*)", "Bash(npm test:*)"],
        "forbidden_bash": _FORBIDDEN,
    }
    violations = check(non_python)
    assert violations == [], (
        "E032: a scoped, forbidden-free non-Python allow-list must pass the "
        f"language-agnostic validator — got {violations!r}"
    )


def test_forbidden_command_in_non_python_list_yields_violation():
    check = _validator()
    tampered = {
        "allowed_tools": ["Read", "Edit"],
        "allowed_bash": ["Bash(go test:*)", "Bash(rm:*)"],
        "forbidden_bash": _FORBIDDEN,
    }
    violations = check(tampered)
    assert violations, (
        "E032: injecting a forbidden command ('Bash(rm:*)') into a non-Python list "
        "must yield a violation — the rule is data-driven, not stack-specific"
    )
    assert any("rm" in v for v in violations), (
        f"E032: the violation must name the offending 'rm' entry — got {violations!r}"
    )


def test_validator_consumes_plain_data_no_source_module():
    """The check takes a plain dict (convention data), proving it does no Python
    source/AST inspection — it is portable to any stack's freedom_layer data."""
    check = _validator()
    # A bare dict with no file path, no module reference — pure data in, list out.
    result = check(
        {
            "allowed_tools": ["Read"],
            "allowed_bash": ["Bash(cargo test:*)"],
            "forbidden_bash": _FORBIDDEN,
        }
    )
    assert isinstance(result, list), (
        f"E032: validator must return a list of violation strings from pure data — got {result!r}"
    )
