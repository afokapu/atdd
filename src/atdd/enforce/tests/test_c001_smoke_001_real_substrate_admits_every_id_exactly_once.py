# URN: test:govern-registry:C001-SMOKE-001-real-substrate-admits-every-id-exactly-once
# Acceptance: acc:govern-registry:C001-SMOKE-001-real-substrate-admits-every-id-exactly-once
# WMBT: wmbt:govern-registry:C001
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
# RED: over the real substrate every one of the duplicated ids raises AmbiguousRuleError
#      the moment .atdd/extensions enters the search roots.
"""SMOKE Test for acc:govern-registry:C001-SMOKE-001-real-substrate-admits-every-id-exactly-once.

Over the toolkit's real substrate no rule_id is admitted from two convention files, and
every one of the real duplicated ids resolves to its core declaration with core's
severity intact.

Drives the real loader over the real trees -- no fixtures, no mocks: the core severity
each id is compared against is read from the live core registry first (default roots),
then the extension tree is added to the roots and every duplicated id is re-resolved.

Contract-schema validation (red.convention validation_levels 5_contract_schema) is
inapplicable here: the acceptance declares no contract_schema, because registry
admission exchanges no I/O document.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import extract_rules
from atdd.enforce.registry import (
    core_rule_ids,
    duplicate_rule_ids,
    extension_rule_ids,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the binding cache between every test case."""
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache()
    yield
    clear_cache()


def test_real_substrate_admits_every_id_exactly_once() -> None:
    from atdd.coach.utils.rule_binding import (
        _ATDD_PKG_DIR,
        bind_rule,
        clear_cache,
    )

    repo = find_repo_root()
    ext_root = repo / ".atdd" / "extensions"

    # GIVEN the real core convention tree and the real vendored extension nodes, with
    # the ids declared in BOTH and each one's CORE severity read from the live
    # core-only registry.
    duplicated = sorted(duplicate_rule_ids(core_rule_ids(), extension_rule_ids(repo)))
    assert duplicated, "no duplicated rule_ids found over the real substrate"

    clear_cache()
    core_severity = {rule_id: bind_rule(rule_id).severity for rule_id in duplicated}

    # WHEN the registry is loaded over roots spanning both the real core tree and the
    # real extension tree, and every rule_id declared in both is resolved.
    clear_cache(override_roots=[_ATDD_PKG_DIR, ext_root])
    resolved = {rule_id: bind_rule(rule_id) for rule_id in duplicated}

    # THEN no id was admitted twice (nothing raised), every one resolves to a source
    # path under the core tree, and no mirror downgraded a severity.
    from_extension = [
        rule_id
        for rule_id, meta in resolved.items()
        if not str(meta.source_path).startswith(str(_ATDD_PKG_DIR))
    ]
    assert not from_extension, f"resolved from the extension tree: {from_extension}"

    downgraded = {
        rule_id: (core_severity[rule_id], meta.severity)
        for rule_id, meta in resolved.items()
        if meta.severity != core_severity[rule_id]
    }
    assert not downgraded, f"severity changed (core, resolved): {downgraded}"

    # AND the extension-only obligations stay bindable. Suppressing the mirrors must
    # not narrow the registry to core: a node that mirrors nothing is a real rule and
    # resolves from the extension tree.
    # Scoped to nodes that are RULES. Five extension-only ids are `kind: family`
    # definition nodes carrying no severity, so _rule_metadata yields nothing for
    # them and they are not bindable by design — asserting otherwise would demand
    # the registry admit a definition as an obligation.
    rule_ids_in_extensions = {
        rule["id"]
        for node in (repo / ".atdd" / "extensions").rglob("*.convention.yaml")
        for _f, _y, rule in extract_rules(node)
        if isinstance(rule.get("id"), str) and isinstance(rule.get("severity"), int)
    }
    extension_only = sorted(rule_ids_in_extensions - core_rule_ids())
    assert extension_only, "no extension-only rule_ids found over the real substrate"
    unbindable = []
    for rule_id in extension_only:
        try:
            meta = bind_rule(rule_id)
        except Exception as exc:  # the failure IS the assertion
            unbindable.append(f"{rule_id}: {type(exc).__name__}")
            continue
        if str(meta.source_path).startswith(str(_ATDD_PKG_DIR)):
            unbindable.append(f"{rule_id}: resolved from core, expected the extension tree")
    assert not unbindable, f"extension-only ids not bindable: {unbindable}"
