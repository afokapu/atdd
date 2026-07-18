# URN: test:govern-registry:E001-SMOKE-001-real-mirrors-all-resolve-to-live-core-rules
# Acceptance: acc:govern-registry:E001-SMOKE-001-real-mirrors-all-resolve-to-live-core-rules
# WMBT: wmbt:govern-registry:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:E001-SMOKE-001-real-mirrors-all-resolve-to-live-core-rules.

Over the toolkit's real substrate every vendored extension node's legacy_rule_id
resolves to a rule that still exists in the live core registry — no mirror drifted.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.registry import (
    core_rule_ids,
    find_mirror_incoherences,
    iter_extension_nodes,
)


def test_real_mirrors_all_resolve_to_live_core_rules() -> None:
    repo = find_repo_root()
    core = core_rule_ids()

    # Every extension mirror still names a live core rule.
    assert find_mirror_incoherences(repo, core) == []

    # And each real node genuinely declares a legacy_rule_id that is a core rule.
    nodes = list(iter_extension_nodes(repo))
    assert nodes, "no extension convention nodes found under .atdd/extensions"
    for node in nodes:
        assert node.legacy_rule_id in core, (
            f"{node.rule_id} legacy_rule_id {node.legacy_rule_id!r} not in core registry"
        )
