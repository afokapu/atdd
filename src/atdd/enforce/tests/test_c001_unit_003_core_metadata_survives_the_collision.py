# URN: test:govern-registry:C001-UNIT-003-core-metadata-survives-the-collision
# Acceptance: acc:govern-registry:C001-UNIT-003-core-metadata-survives-the-collision
# WMBT: wmbt:govern-registry:C001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
# RED: admission is by file, not by provenance, so bind_rule raises AmbiguousRuleError
#      over the two roots and no metadata is resolved at all.
"""GREEN Test for acc:govern-registry:C001-UNIT-003-core-metadata-survives-the-collision.

For a doubly-declared rule_id the resolved severity, disposition and validator ref are
the CORE values, so admission never silently adopts a mirror's weaker metadata.

The fixture reproduces the real drift measured across the 32 duplicated ids: the mirror
carries a LOWER severity and a validator ref that names no test function (it echoes a
rule_id, which parse_validator_field rejects), while core carries the stricter severity
and the executable module::function ref.

Contract-schema validation (red.convention validation_levels 5_contract_schema) is
inapplicable here: the acceptance declares no contract_schema, because registry
admission exchanges no I/O document.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SECURITY_RULE = "coder.fixture.sql-injection"
CORE_SEVERITY = 5
CORE_VALIDATOR = "test_fixture_detector::test_no_sql_injection"
CORE_DISPOSITION = "strict"
MIRROR_SEVERITY = 4


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the binding cache between every test case."""
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache()
    yield
    clear_cache()


def _write_core_declaration(core_root: Path) -> Path:
    """The core declaration: stricter severity, executable validator ref."""
    core_root.mkdir(parents=True, exist_ok=True)
    node = core_root / f"{SECURITY_RULE}.convention.yaml"
    node.write_text(
        "schema_version: '1.0.0'\nkind: rule\n"
        f"rule_id: {SECURITY_RULE}\n"
        "statement: the core declaration of a mirrored security rule\n"
        "implementation:\n  type: validator\n"
        f"  ref: {CORE_VALIDATOR}\n"
        f"metadata:\n  severity: {CORE_SEVERITY}\n  disposition: {CORE_DISPOSITION}\n",
        encoding="utf-8",
    )
    return node


def _write_weaker_mirror(project_root: Path) -> Path:
    """A mirror of the same rule carrying the weaker metadata the real mirrors carry.

    Hand-rolled rather than reusing ``write_mirror_node``: that builder pins
    ``severity: 3`` and ships no ``implementation`` block, and this acceptance turns on
    the mirror's severity being LOWER than core's and its validator ref naming no test.
    """
    node_dir = project_root / ".atdd" / "extensions" / "atdd.extension.coder" / "0.1.0" / "conventions"
    node_dir.mkdir(parents=True, exist_ok=True)
    node = node_dir / f"{SECURITY_RULE}.convention.yaml"
    node.write_text(
        "schema_version: '1.1.0'\nkind: rule\n"
        f"rule_id: {SECURITY_RULE}\n"
        "statement: the extension mirror of the same rule\n"
        "implementation:\n  type: validator\n"
        f"  ref: {SECURITY_RULE}\n"
        f"metadata:\n  severity: {MIRROR_SEVERITY}\n  disposition: advisory\n"
        "source:\n"
        "  legacy_path: src/atdd/coder/conventions/security.convention.yaml\n"
        f"  legacy_rule_id: {SECURITY_RULE}\n"
        "  extraction_mode: high_fidelity\n",
        encoding="utf-8",
    )
    return node


def test_core_metadata_survives_the_collision(tmp_path: Path) -> None:
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    # GIVEN a core declaration carrying severity 5 and an executable module::function
    # validator ref, and a mirror of that rule_id carrying severity 4 and a validator
    # ref that names no test function.
    core_root = tmp_path / "core" / "atdd"
    core_node = _write_core_declaration(core_root)
    _write_weaker_mirror(tmp_path)
    ext_root = tmp_path / ".atdd" / "extensions"

    # WHEN the rule_id is resolved over roots spanning both trees.
    clear_cache(override_roots=[core_root, ext_root])
    meta = bind_rule(SECURITY_RULE)

    # THEN every field enforcement reads is the CORE value -- the mirror downgrades
    # nothing.
    assert meta.source_path == core_node
    assert meta.severity == CORE_SEVERITY
    assert meta.validator == CORE_VALIDATOR
    assert meta.disposition == CORE_DISPOSITION
