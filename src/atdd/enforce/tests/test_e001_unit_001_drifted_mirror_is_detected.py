# URN: test:govern-registry:E001-UNIT-001-drifted-mirror-is-detected
# Acceptance: acc:govern-registry:E001-UNIT-001-drifted-mirror-is-detected
# WMBT: wmbt:govern-registry:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E001-UNIT-001-drifted-mirror-is-detected.

An extension node whose ``source.legacy_rule_id`` names a core rule absent from the
registry is reported as a drifted mirror; a node whose legacy_rule_id resolves to a
live core rule is not.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.registry import find_mirror_incoherences

from .conftest import write_mirror_node


def test_drifted_mirror_is_detected(tmp_path: Path) -> None:
    core_ids = {"coder.refactor.complexity-cognitive"}

    # Coherent: its legacy_rule_id is a live core rule.
    write_mirror_node(
        tmp_path,
        rule_id="coder.refactor.complexity-cognitive",
        legacy_rule_id="coder.refactor.complexity-cognitive",
    )
    # Drifted: its legacy_rule_id names a core rule that no longer exists.
    write_mirror_node(
        tmp_path,
        rule_id="coder.refactor.complexity-gone",
        legacy_rule_id="coder.refactor.complexity-gone",
    )

    incoherences = find_mirror_incoherences(tmp_path, core_ids)

    ext_ids = {m.extension_rule_id for m in incoherences}
    assert ext_ids == {"coder.refactor.complexity-gone"}
    # The report names both the extension id and the missing legacy_rule_id.
    (drift,) = incoherences
    assert drift.legacy_rule_id == "coder.refactor.complexity-gone"
