# URN: test:bind-extension-conventions:bind-extension-conventions:E002-SMOKE-001-live-gating-coverage-is-clean-after-fanout
# Acceptance: acc:bind-extension-conventions:E002-SMOKE-001-live-gating-coverage-is-clean-after-fanout
# WMBT: wmbt:bind-extension-conventions:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:bind-extension-conventions:E002-SMOKE-001-live-gating-coverage-is-clean-after-fanout.

Over the toolkit's own real committed nodes and regenerated
``.atdd/binding.lock.yaml``, the gating-coverage validator returns clean: every
gating extension node is bound, the documentation-only nodes stay exempt, and no
bound entry resolves to an obligation declared nowhere in the core-or-extension
node universe.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.gating import (
    assert_gating_coverage,
    find_unbound_gating_nodes,
    find_undeclared_bindings,
)
from atdd.enforce.runner import resolve_substrate_home


def test_live_gating_coverage_is_clean_after_fanout() -> None:
    repo_root = find_repo_root()
    substrate_home = resolve_substrate_home(repo_root)

    # The loud guard raises nothing over the real substrate.
    assert_gating_coverage(substrate_home, repo_root)

    # And the underlying reports are both empty.
    from atdd.enforce.binding_gap import load_bound_convention_ids, load_declared_extension_nodes
    from atdd.enforce.gating import load_core_node_ids

    declared = load_declared_extension_nodes(substrate_home)
    bound = load_bound_convention_ids(substrate_home)
    universe = set(declared) | load_core_node_ids(repo_root)

    assert find_unbound_gating_nodes(declared, bound) == []
    assert find_undeclared_bindings(bound, universe) == []
    # The two documentation-only nodes remain unbound without being flagged.
    assert "coder.performance.perf" not in bound
    assert "tester.migration.naming" not in bound
