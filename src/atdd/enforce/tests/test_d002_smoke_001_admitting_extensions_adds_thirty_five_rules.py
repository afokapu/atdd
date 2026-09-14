# URN: test:govern-registry:D002-SMOKE-001-admitting-extensions-adds-thirty-five-rules
# Acceptance: acc:govern-registry:D002-SMOKE-001-admitting-extensions-adds-thirty-five-rules
# WMBT: wmbt:govern-registry:D002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:D002-SMOKE-001-admitting-extensions-adds-thirty-five-rules.

The explicit superseded evidence retiring D001's premise. D001 records that admitting
the extension tree "would add NO new rule and only duplicate ids". Over the real
substrate that is false: the extension-only set is non-empty, every member of it
mirrors no live core rule, and admitting them therefore creates no ADDITIONAL
duplicate beyond the mirrors already counted by #1973.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.registry import (
    core_rule_ids,
    duplicate_rule_ids,
    extension_rule_ids,
    iter_extension_nodes,
    new_rules_from_extensions,
)


def test_admitting_extensions_adds_thirty_five_rules() -> None:
    repo = find_repo_root()
    core = core_rule_ids()
    ext = extension_rule_ids(repo)
    assert ext, "no extension convention nodes found under .atdd/extensions"

    new = new_rules_from_extensions(core, ext)

    # D001's premise is expired: the extension-only set is NOT empty.
    assert new, "D001's premise would hold — no evidence of supersession"
    assert len(new) == 35, f"expected 35 extension-only rule_ids, measured {len(new)}"

    # Every one of the 35 mirrors no live core rule, so none is a second declaration.
    by_id = {n.rule_id: n for n in iter_extension_nodes(repo)}
    for rule_id in sorted(new):
        legacy = by_id[rule_id].legacy_rule_id
        assert legacy not in core, (
            f"{rule_id} claims to mirror live core rule {legacy!r}; it is not extension-only"
        )

    # So admitting them adds no duplicate: the collisions are exactly the mirror set.
    assert duplicate_rule_ids(core, ext) & new == set(), (
        "an extension-only rule_id also collides with core — admitting it would duplicate"
    )
