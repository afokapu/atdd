# URN: test:bind-extension-conventions:bind-extension-conventions:E002-UNIT-002-binding-with-no-declared-node-is-flagged
# Acceptance: acc:bind-extension-conventions:E002-UNIT-002-binding-with-no-declared-node-is-flagged
# WMBT: wmbt:bind-extension-conventions:E002
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""RED Test for acc:bind-extension-conventions:E002-UNIT-002-binding-with-no-declared-node-is-flagged.

A bound entry whose obligation is declared NOWHERE in the node universe is
flagged as bound-not-declared; a binding declared in core (or in extensions) is
accepted — the full-universe check that tolerates the core-declared tester
bindings while catching a truly orphaned one.
"""
from __future__ import annotations

from atdd.enforce.gating import find_undeclared_bindings


def test_binding_with_no_declared_node_is_flagged() -> None:
    declared_universe = {"core.only.node", "ext.node"}
    bound = {"core.only.node", "ext.node", "declared.nowhere"}

    undeclared = find_undeclared_bindings(bound, declared_universe)

    # Only the binding declared nowhere is reported.
    assert undeclared == ["declared.nowhere"]
    # A binding declared only in core (not extensions) is NOT reported.
    assert "core.only.node" not in undeclared
