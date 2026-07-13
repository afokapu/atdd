# URN: test:govern-projection-fields:merge-projection-objects:R001-UNIT-002-green-actionable-conflict-report
# Acceptance: acc:govern-projection-fields:R001-UNIT-002-green-actionable-conflict-report
# WMBT: wmbt:govern-projection-fields:R001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: every unsafe divergence — a divergent body, a divergent train digest, an evidence-less phase advance — exits non-zero, writes no merged file, and reports the offending field, the writer on each side and the failing ownership or evidence rule; no report resolves a phase divergence by selecting the numerically further phase Refs #1400.
"""Every unsafe triple is refused, and every refusal is actionable (R001-UNIT-002).

wagon: govern-projection-fields | feature: merge-projection-objects | phase: RED
WMBT: wmbt:govern-projection-fields:R001

Three unsafe divergences, one per class of rule: a **body** two people rewrote, a **train**
two people set differently, and a **phase** somebody advanced without the evidence. Each has
to fail the same way — non-zero, no merged file on disk, and a report naming the field, both
writers, and the rule.

The last assertion is the one that keeps the whole model honest: no report resolves a phase
divergence by picking the further phase. Not as a fallback, not as a hint, not as a
"suggestion" the operator will accept because it is there.
"""
from __future__ import annotations

from atdd.state import merge_driver, ownership
from atdd.state.merge_driver import MergeResult
from atdd.state.ownership import (
    RULE_MONOTONIC_GATED,
    RULE_SAME_DIGEST,
    RULE_SINGLE_OWNER,
)

from ._helpers import PLANNED_TO_RED, UID_X, document, write_document

UNSAFE = {
    "divergent body": dict(
        base=document(body="original", owner_actor="dev-a"),
        ours=document(body="A's rewrite", owner_actor="dev-a"),
        theirs=document(body="B's rewrite", owner_actor="dev-b"),
        field="body", rule=RULE_SINGLE_OWNER, writers=("dev-a", "dev-b"),
    ),
    "divergent train digest": dict(
        base=document(train=None, owner_actor="dev-a"),
        ours=document(train="train:commons:spine", owner_actor="dev-a"),
        theirs=document(train="train:commons:other", owner_actor="dev-b"),
        field="train", rule=RULE_SAME_DIGEST, writers=("dev-a", "dev-b"),
    ),
    "evidence-less phase advance": dict(
        base=document(phase="PLANNED", owner_actor="dev-a", last_lifecycle_actor="dev-a"),
        ours=document(phase="RED", owner_actor="dev-a", last_lifecycle_actor="dev-a"),
        theirs=document(phase="GREEN", owner_actor="dev-b", last_lifecycle_actor="dev-b"),
        field="phase", rule=RULE_MONOTONIC_GATED, writers=("dev-a", "dev-b"),
    ),
}


def test_r001_unit_002_green_actionable_conflict_report(tmp_path) -> None:
    """Each unsafe triple: non-zero, no merged file, and a report naming everything needed."""
    policy = ownership.default_policy()
    reports = []

    for case, triple in UNSAFE.items():
        ours_path = write_document(tmp_path / case / f"{UID_X}.yaml", triple["ours"])
        before = ours_path.read_bytes()

        result: MergeResult = merge_driver.merge_files(
            write_document(tmp_path / case / "base.yaml", triple["base"]),
            ours_path,
            write_document(tmp_path / case / "theirs.yaml", triple["theirs"]),
            policy=policy,
            ours_evidence=PLANNED_TO_RED,
            theirs_evidence=(),
        )

        # Exits non-zero, and writes NO merged file: a "best effort" merge on conflict would be
        # picking a winner with extra steps.
        assert result.exit_code == 1, case
        assert result.merged is None, case
        assert ours_path.read_bytes() == before, f"{case}: the driver wrote over ours"

        conflict = next(c for c in result.conflicts if c.field == triple["field"])
        assert conflict.rule == triple["rule"], case
        assert (conflict.ours_writer, conflict.theirs_writer) == triple["writers"], case

        rendered = result.render()
        for fragment in (triple["field"], triple["rule"], *triple["writers"]):
            assert fragment in rendered, f"{case}: the report never names {fragment}"
        reports.append((case, rendered))

    # No report resolves the phase divergence by selecting the numerically further phase: the
    # merged document does not exist, and the report says so in as many words.
    phase_case = dict(reports)["evidence-less phase advance"]
    assert "does not resolve a phase divergence by taking the further phase" in phase_case
    assert "never picks a winner" in phase_case
