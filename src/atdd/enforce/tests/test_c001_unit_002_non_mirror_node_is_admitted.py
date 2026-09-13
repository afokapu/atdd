# URN: test:govern-registry:C001-UNIT-002-non-mirror-node-is-admitted
# Acceptance: acc:govern-registry:C001-UNIT-002-non-mirror-node-is-admitted
# WMBT: wmbt:govern-registry:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
# RED: this acceptance is a NON-REGRESSION guard and is green before the change --
#      an id declared once already resolves. It exists so provenance-aware admission
#      cannot be implemented by excluding the extension tree wholesale, which would
#      turn it red. Recorded rather than forced: see the test body.
"""GREEN Test for acc:govern-registry:C001-UNIT-002-non-mirror-node-is-admitted.

An extension node whose source.legacy_rule_id names no live core rule is a genuinely
new obligation and IS admitted, so provenance-aware admission narrows nothing it
should not.

Contract-schema validation (red.convention validation_levels 5_contract_schema) is
inapplicable here: the acceptance declares no contract_schema, because registry
admission exchanges no I/O document.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import write_mirror_node

CORE_RULE = "coder.fixture.core-only"
EXTENSION_ONLY_RULE = "coder.fixture.extension-only"


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the binding cache between every test case."""
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache()
    yield
    clear_cache()


def _write_core_declaration(core_root: Path, rule_id: str) -> Path:
    """A core convention node declaring *rule_id*."""
    core_root.mkdir(parents=True, exist_ok=True)
    node = core_root / f"{rule_id}.convention.yaml"
    node.write_text(
        "schema_version: '1.0.0'\nkind: rule\n"
        f"rule_id: {rule_id}\n"
        "statement: a core rule the extension does not mirror\n"
        "implementation:\n  type: validator\n  ref: test_fixture_detector::test_core_only\n"
        "metadata:\n  severity: 3\n  disposition: strict\n",
        encoding="utf-8",
    )
    return node


def test_non_mirror_node_is_admitted(tmp_path: Path) -> None:
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    # GIVEN a core tree, and an extension node declaring a rule_id the core tree does
    # NOT declare, whose source.legacy_rule_id names no rule in the core tree. The
    # legacy_rule_id echoes its own id, which is the shape the 35 real non-mirror
    # nodes carry.
    core_root = tmp_path / "core" / "atdd"
    _write_core_declaration(core_root, CORE_RULE)
    ext_node = write_mirror_node(
        tmp_path,
        rule_id=EXTENSION_ONLY_RULE,
        legacy_rule_id=EXTENSION_ONLY_RULE,
    )
    ext_root = tmp_path / ".atdd" / "extensions"

    # WHEN the registry is loaded over roots spanning both trees.
    clear_cache(override_roots=[core_root, ext_root])
    meta = bind_rule(EXTENSION_ONLY_RULE)

    # THEN the rule resolves, naming the EXTENSION node as its source path -- an
    # extension-declared obligation is bindable when it mirrors nothing.
    assert meta.source_path == ext_node
    assert ".atdd/extensions" in str(meta.source_path)
