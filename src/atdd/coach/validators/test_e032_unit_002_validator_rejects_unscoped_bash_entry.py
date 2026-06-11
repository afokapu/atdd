# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E032-UNIT-002-validator-rejects-unscoped-bash-entry
# Acceptance: acc:spawn-agents:E032-UNIT-002-validator-rejects-unscoped-bash-entry
# WMBT: wmbt:spawn-agents:E032
# Phase: GREEN
# Assertion: behavioral
"""E032-UNIT-002 — the validator fails when a Bash allow-list entry is not tightly
scoped: bare 'Bash', 'Bash(*)' and 'Bash(:*)' are rejected; only Bash(<cmd>:*) is
accepted.

RED: the flipped validator does not exist yet. GREEN: every allowed_bash entry must
match the scoped Bash(cmd:*) shape (prefix-injection guard — a loose prefix can be
chained, e.g. 'pytest && rm -rf').
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.coder]


_FORBIDDEN = ["git push", "git commit", "rm", "gh", "sudo"]


def _validator():
    from atdd.coach.validators.freedom_layer_validator import (
        check_freedom_layer_allowlist_safety,
    )

    return check_freedom_layer_allowlist_safety


@pytest.mark.parametrize("unscoped", ["Bash", "Bash(*)", "Bash(:*)"])
def test_unscoped_bash_entry_yields_violation(unscoped):
    check = _validator()
    freedom_layer = {
        "allowed_tools": ["Read"],
        "allowed_bash": ["Bash(pytest:*)", unscoped],
        "forbidden_bash": _FORBIDDEN,
    }
    violations = check(freedom_layer)
    assert violations, (
        f"E032: unscoped/over-broad Bash entry {unscoped!r} must yield a violation"
    )
    assert any(unscoped in v or "scope" in v.lower() or "broad" in v.lower() for v in violations), (
        f"E032: a violation must reference the unscoped/over-broad entry {unscoped!r} "
        f"— got {violations!r}"
    )


def test_well_formed_scoped_entry_yields_no_violation():
    check = _validator()
    freedom_layer = {
        "allowed_tools": ["Read"],
        "allowed_bash": ["Bash(pytest:*)"],
        "forbidden_bash": _FORBIDDEN,
    }
    violations = check(freedom_layer)
    assert violations == [], (
        f"E032: a tightly-scoped 'Bash(pytest:*)' must produce no violation — got {violations!r}"
    )
