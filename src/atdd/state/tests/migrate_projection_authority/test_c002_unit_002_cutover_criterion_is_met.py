# URN: test:migrate-projection-authority:migrate-store-projection:C002-UNIT-002-cutover-criterion-is-met
# Acceptance: acc:migrate-projection-authority:C002-UNIT-002-cutover-criterion-is-met
# WMBT: wmbt:migrate-projection-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: The M8 exit criterion 'projection-is-shared-state' must report met. It is the migration's own exit test, and it is the one of three that fails — the two irreversible steps already report met while their reversible prerequisite never landed. Refs #1622.

"""The projection-is-shared-state criterion must report met (C002-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:C002

`atdd state cutover` is the milestone's own exit test — it exists, per its module
docstring, because "a milestone whose exit criteria live only in a document is a
milestone that gets declared done by assertion."

Two of its three criteria already report met: `github-is-optional-mirror` and
`manifest-is-not-a-fallback`, corresponding to rollout steps 40 and 50 — both of
which are marked **irreversible** in `.atdd/policy/migration-rollout.yaml`. The
third, `projection-is-shared-state`, corresponds to step 20, which is reversible
and never landed. The one-way doors were walked through while the prerequisite that
made them safe was skipped.

RED: a repo with no committed projection reports the criterion unmet, and says so
in exactly those words. That verdict is the acceptance — CORE-036 is what turns it
over.
"""
from __future__ import annotations

from atdd.state import cutover


def test_projection_is_shared_state_reports_met(tmp_path) -> None:
    """A repo whose store has been migrated reports all three M8 criteria met."""
    report = cutover.check(tmp_path, projection_dir=tmp_path / ".atdd/state/projection")

    verdicts = {criterion.name: criterion for criterion in report.criteria}
    assert set(verdicts) == set(cutover.CRITERIA), "every criterion must be evaluated"

    projection = verdicts[cutover.CRITERION_PROJECTION]
    assert projection.met, (
        "the projection is not shared state, so the migration has not finished: "
        f"{projection.render()}"
    )

    assert report.met, f"M8 is not complete: {report.render()}"
    assert report.exit_code == 0
