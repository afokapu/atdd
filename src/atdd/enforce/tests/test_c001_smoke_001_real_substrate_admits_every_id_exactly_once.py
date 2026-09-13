# URN: test:govern-registry:C001-SMOKE-001-real-substrate-admits-every-id-exactly-once
# Acceptance: acc:govern-registry:C001-SMOKE-001-real-substrate-admits-every-id-exactly-once
# WMBT: wmbt:govern-registry:C001
# Phase: SMOKE
# Layer: integration
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
