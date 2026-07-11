# URN: test:govern-projection-fields:merge-projection-objects:E002-UNIT-002-green-auto-merges-the-three-safe-cases
# Acceptance: acc:govern-projection-fields:E002-UNIT-002-green-auto-merges-the-three-safe-cases
# WMBT: wmbt:govern-projection-fields:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the merge driver auto-merges same-object divergence in the three safe cases only — identical transitions, a strict no-op side, and a further phase carrying evidence for every skipped gate — each exiting zero with no conflict markers, each merged object byte-identical to the deterministic projection of the merged state, and disjoint-field edits merging without conflict Refs #1400.
"""The three safe cases merge, and the bytes are the projector's own (E002-UNIT-002).

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:E002

Spec §7.2 admits exactly three same-object merges: identical transitions, a strict no-op side,
and a further phase carrying verifiable evidence for every skipped gate. Anything else is an
operator's decision, not a driver's.

The second assertion is the one that is easy to miss and expensive to lose: the merged file
must be **byte-identical to the projection of the merged state**. A driver that produced a
merged document which was correct but not canonical would hand the next CI run a projection
that fails ``project(hydrate(p)) == p`` — the merge would pass and the branch would be
unmergeable, for reasons pointing at the wrong file (I1).
"""
from __future__ import annotations

from atdd.state import merge_driver
from atdd.state.projection import canonical_bytes

from ._helpers import PLANNED_TO_GREEN, PLANNED_TO_RED, UID_X, document, write_document


def test_e002_unit_002_green_auto_merges_the_three_safe_cases(tmp_path) -> None:
    """Identical, no-op, evidence-backed — all three merge; and the bytes stay canonical."""
    base = document(phase="PLANNED")

    triples = {
        # 1. Identical transitions: both sides walked PLANNED -> RED.
        "identical": (document(phase="RED"), document(phase="RED"), PLANNED_TO_RED, "RED"),
        # 2. A strict no-op: theirs did not move the object at all.
        "no-op": (document(phase="RED"), document(phase="PLANNED"), PLANNED_TO_RED, "RED"),
        # 3. A further phase with evidence for every gate it skipped.
        "evidence-backed": (
            document(phase="RED"), document(phase="GREEN"), PLANNED_TO_GREEN, "GREEN"),
    }

    for case, (ours, theirs, theirs_evidence, expected) in triples.items():
        result = merge_driver.merge_object(
            UID_X, base, ours, theirs,
            ours_evidence=PLANNED_TO_RED, theirs_evidence=theirs_evidence,
        )
        assert result.ok, f"{case}: {result.render()}"
        assert result.exit_code == 0
        assert result.merged["phase"] == expected, case

        # Written through the real file driver: exit zero, and no conflict markers anywhere.
        ours_path = write_document(tmp_path / case / "ours.yaml", ours)
        base_path = write_document(tmp_path / case / "base.yaml", base)
        theirs_path = write_document(tmp_path / case / "theirs.yaml", theirs)
        written = merge_driver.merge_files(
            base_path, ours_path, theirs_path,
            ours_evidence=PLANNED_TO_RED, theirs_evidence=theirs_evidence,
        )
        assert written.exit_code == 0, case
        merged_bytes = ours_path.read_bytes()
        assert b"<<<<<<<" not in merged_bytes and b">>>>>>>" not in merged_bytes

        # The merged file IS the canonical projection of the merged state, byte for byte.
        assert merged_bytes == canonical_bytes(written.merged), case

    # Disjoint-field edits on the SAME object merge without conflict: A renames it while B
    # moves the phase, and neither has anything to say about the other's field.
    disjoint = merge_driver.merge_object(
        UID_X, base,
        document(slug="renamed-by-a"),
        document(phase="RED"),
        theirs_evidence=PLANNED_TO_RED,
    )
    assert disjoint.ok, disjoint.render()
    assert disjoint.merged["slug"] == "renamed-by-a"
    assert disjoint.merged["phase"] == "RED"
