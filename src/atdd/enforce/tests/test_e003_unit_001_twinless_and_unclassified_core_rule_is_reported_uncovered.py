# URN: test:govern-registry:E003-UNIT-001-twinless-and-unclassified-core-rule-is-reported-uncovered
# Acceptance: acc:govern-registry:E003-UNIT-001-twinless-and-unclassified-core-rule-is-reported-uncovered
# WMBT: wmbt:govern-registry:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E003-UNIT-001-twinless-and-unclassified-core-rule-is-reported-uncovered.

A core rule is covered by an extension twin OR by a why-not verdict in the
classification record. A rule with neither is reported uncovered BY NAME, and the
two ways of being covered are attributed apart — which is the whole point: a
mirrored obligation moved with its enforcement, a classified one was adjudicated
never to move, and conflating them would let an unexamined rule pass as settled.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.twin_coverage import (
    COVERED_BY_RECORD,
    COVERED_BY_TWIN,
    measure_twin_coverage,
    twins_by_core_rule,
    why_not_verdicts,
)

from .conftest import write_mirror_node

_MIRRORED = "coder.refactor.nplus1"
_CLASSIFIED = "coder.state-store.work-item-provenance"
_NEITHER = "coder.dto.boundary-crossing"


def test_twinless_and_unclassified_core_rule_is_reported_uncovered(tmp_path: Path) -> None:
    core_ids = [_MIRRORED, _CLASSIFIED, _NEITHER]

    # An extension node mirrors the first, declaring it as its legacy_rule_id.
    write_mirror_node(tmp_path, rule_id=_MIRRORED, legacy_rule_id=_MIRRORED)

    # The classification record carries a why-not verdict for the second.
    record = tmp_path / "classification.md"
    record.write_text(
        "| rule_id | verdict | disposition | Quoted evidence |\n"
        "|---|---|---|---|\n"
        f"| `{_CLASSIFIED}` | ATDD-INTERNAL | advisory | "
        '"Every `work_item` in the State Store has a sanctioned authoring event." |\n',
        encoding="utf-8",
    )

    coverage = measure_twin_coverage(
        core_ids,
        twins=twins_by_core_rule(tmp_path),
        why_not=why_not_verdicts(record),
    )

    # The rule with neither is the ONLY one reported uncovered, and it is named.
    assert coverage.uncovered == (_NEITHER,)

    by_id = {record_.rule_id: record_ for record_ in coverage.covered}

    # Attributed to its twin, which is named — not to the record.
    assert by_id[_MIRRORED].covered_by == COVERED_BY_TWIN
    assert by_id[_MIRRORED].twins == (_MIRRORED,)

    # Attributed to the record — not to a twin, of which it has none.
    assert by_id[_CLASSIFIED].covered_by == COVERED_BY_RECORD
    assert by_id[_CLASSIFIED].twins == ()

    # The partition of the core set is exact: every rule is covered or uncovered,
    # exactly once. A rule counted twice would understate the shortfall.
    assert len(by_id) == len(coverage.covered), "a rule is reported covered twice"
    assert set(by_id) | set(coverage.uncovered) == set(core_ids)
    assert len(coverage.covered) + len(coverage.uncovered) == len(coverage.core_surface) == 3

    # A shortfall of any size refuses the move-ready certification.
    assert coverage.move_ready is False
