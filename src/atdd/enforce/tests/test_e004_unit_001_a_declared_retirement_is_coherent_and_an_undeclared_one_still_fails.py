# URN: test:govern-registry:E004-UNIT-001-a-declared-retirement-is-coherent-and-an-undeclared-one-still-fails
# Acceptance: acc:govern-registry:E004-UNIT-001-a-declared-retirement-is-coherent-and-an-undeclared-one-still-fails
# WMBT: wmbt:govern-registry:E004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E004-UNIT-001-a-declared-retirement-is-coherent-and-an-undeclared-one-still-fails.

The discrimination itself. Two extension nodes are indistinguishable in shape — each
declares a ``source.legacy_rule_id`` naming a core rule that is not in the registry.
One of those core rules is declared retired; the other is not. That declaration is the
only thing separating a completed carve-out from a stale mirror, and it has to be the
only thing that separates the verdicts too.

The second assertion is the one that keeps this honest: declaring a retirement must
not become a way to forgive drift in general.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.registry import find_mirror_incoherences
from atdd.enforce.retirements import declared_retirements

from .conftest import write_mirror_node, write_retirement_ledger

_LIVE = "coder.refactor.complexity-cognitive"
_RETIRED = "coder.design.token-color"
_RENAMED = "coder.refactor.complexity-gone"


def test_a_declared_retirement_is_coherent_and_an_undeclared_one_still_fails(
    tmp_path: Path,
) -> None:
    core_ids = {_LIVE}

    # Never drifted: its legacy_rule_id is a live core rule.
    write_mirror_node(tmp_path, rule_id=_LIVE, legacy_rule_id=_LIVE)
    # A completed carve-out: core deliberately deleted the rule this node superseded.
    write_mirror_node(tmp_path, rule_id=_RETIRED, legacy_rule_id=_RETIRED)
    # A stale mirror: the core rule was renamed and nobody repointed this node.
    write_mirror_node(tmp_path, rule_id=_RENAMED, legacy_rule_id=_RENAMED)

    write_retirement_ledger(
        tmp_path,
        {
            _RETIRED: {
                "retired_in": "#1518",
                "superseded_by": [_RETIRED],
            }
        },
    )

    retirements = declared_retirements(tmp_path)
    assert set(retirements) == {_RETIRED}
    assert retirements[_RETIRED].retired_in == "#1518"
    assert retirements[_RETIRED].superseded_by == (_RETIRED,)

    reported = {
        m.extension_rule_id
        for m in find_mirror_incoherences(tmp_path, core_ids, retirements=retirements)
    }

    # The declared retirement is the expected end state, not a fault.
    assert _RETIRED not in reported
    # The undeclared one is still a loud failure — a rename must not ride along.
    assert reported == {_RENAMED}

    # And the ledger changes nothing for a mirror that never drifted: it is absent
    # from the findings with and without the ledger.
    assert _LIVE not in reported
    assert _LIVE not in {
        m.extension_rule_id for m in find_mirror_incoherences(tmp_path, core_ids)
    }
