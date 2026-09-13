# URN: test:govern-registry:C001-UNIT-001-mirror-node-is-not-admitted-as-a-second-declaration
# Acceptance: acc:govern-registry:C001-UNIT-001-mirror-node-is-not-admitted-as-a-second-declaration
# WMBT: wmbt:govern-registry:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
# RED: admission is by file, not by provenance, so the mirror is a rival declaration
#      and bind_rule raises AmbiguousRuleError over the two roots.
"""GREEN Test for acc:govern-registry:C001-UNIT-001-mirror-node-is-not-admitted-as-a-second-declaration.

An extension node whose source.legacy_rule_id names a live core rule contributes no
declaration of that rule_id, so the id resolves to its core declaration and the
collision never arises.

Contract-schema validation (red.convention validation_levels 5_contract_schema) is
inapplicable here: the acceptance declares no contract_schema, because registry
admission exchanges no I/O document — the assertion surface is bind_rule's resolved
RuleMetadata, asserted behaviourally.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import write_mirror_node

MIRRORED_RULE = "coder.fixture.mirrored"


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the binding cache between every test case."""
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache()
    yield
    clear_cache()


def _write_core_declaration(core_root: Path, rule_id: str) -> Path:
    """A core convention node declaring *rule_id* with an executable validator ref."""
    core_root.mkdir(parents=True, exist_ok=True)
    node = core_root / f"{rule_id}.convention.yaml"
    node.write_text(
        "schema_version: '1.0.0'\nkind: rule\n"
        f"rule_id: {rule_id}\n"
        "statement: the core declaration of a mirrored rule\n"
        "implementation:\n  type: validator\n  ref: test_fixture_detector::test_core_obligation\n"
        "metadata:\n  severity: 5\n  disposition: strict\n",
        encoding="utf-8",
    )
    return node


def test_mirror_node_is_not_admitted_as_a_second_declaration(tmp_path: Path) -> None:
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    # GIVEN a core tree declaring the rule, and an extension node mirroring it
    # (source.legacy_rule_id naming that same live core rule).
    core_root = tmp_path / "core" / "atdd"
    core_node = _write_core_declaration(core_root, MIRRORED_RULE)
    write_mirror_node(tmp_path, rule_id=MIRRORED_RULE, legacy_rule_id=MIRRORED_RULE)
    ext_root = tmp_path / ".atdd" / "extensions"

    # WHEN the registry is loaded over roots spanning both trees.
    clear_cache(override_roots=[core_root, ext_root])
    meta = bind_rule(MIRRORED_RULE)

    # THEN the rule resolves to its CORE declaration, and the mirror contributed
    # no second declaration of it.
    assert meta.source_path == core_node
    assert ".atdd/extensions" not in str(meta.source_path)
