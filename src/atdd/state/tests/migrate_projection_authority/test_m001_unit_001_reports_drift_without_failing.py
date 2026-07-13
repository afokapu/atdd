# URN: test:migrate-projection-authority:compare-shadow-projection:M001-UNIT-001-reports-drift-without-failing
# Acceptance: acc:migrate-projection-authority:M001-UNIT-001-reports-drift-without-failing
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A repo whose committed projection disagrees with project(store) for one work item has its drift REPORTED — the uid and the differing fields, against both the committed and the manifest-derived projections — and the check still EXITS ZERO, because shadow mode may not block a merge while the cutover is staged. Refs #1434.
"""Shadow mode reports drift and still exits zero (M001-UNIT-001).

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:M001

The exit code is the design, and it reads like a bug to anyone who skims it. A shadow check that
could fail a build is a blocking check with a misleading name: it would demand the trust that the
shadow window exists to *earn*. Flip the gate on day one and the first unnoticed drift stops every
merge in the repo; leave it off entirely and the drift accumulates unseen until the day you do flip
it, when every branch is red at once and nobody knows which one broke it.

So the two halves are asserted together, and they must both hold or the instrument is useless: the
drift is reported **precisely** (which uid, which fields, both sides), and the run is **harmless**.
Refs #1434 / #1400.
"""
from __future__ import annotations

from atdd.state import shadow
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import canonical_bytes, project

from ._helpers import UID_A, UID_B, control_root, memory_store

_BASE = {"slug": "alpha", "owner_actor": "dev-a", "state": "ACTIVE", "wmbts": []}


def test_m001_unit_001_reports_drift_without_failing(tmp_path) -> None:
    """One drifted work item is reported by uid and field — and the check exits 0 anyway."""
    root = control_root(tmp_path / "repo")
    projection = root / ".atdd" / "state" / "projection"

    with memory_store() as (_conn, store):
        store.objects.upsert(UID_A, WORK_ITEM_KIND, state="PLANNED", data=dict(_BASE))
        store.objects.upsert(UID_B, WORK_ITEM_KIND, state="GREEN",
                             data={**_BASE, "slug": "beta"})
        project(store, projection)

        # Now the store moves on and the committed projection does not: alpha advances
        # PLANNED → RED and its owner changes. That is exactly the drift the blocking gate will
        # later refuse — and exactly what shadow mode exists to show you first.
        store.objects.upsert(UID_A, WORK_ITEM_KIND, state="RED",
                             data={**_BASE, "owner_actor": "dev-b"})

        report = shadow.compare(store, root=root, projection_dir=projection,
                                sources=[shadow.SOURCE_COMMITTED])

    # REPORTED — by uid, by field, with both sides.
    assert not report.clean
    drifts = report.for_source(shadow.SOURCE_COMMITTED)
    assert len(drifts) == 1, [d.render() for d in drifts]
    drift = drifts[0]
    assert drift.uid == UID_A
    assert set(drift.fields) == {"phase", "owner_actor"}
    assert drift.fields["phase"] == ("RED", "PLANNED")           # (store, committed)
    assert drift.fields["owner_actor"] == ("dev-b", "dev-a")
    assert UID_A in drift.render() and "phase" in drift.render()

    # beta did NOT drift, and is not reported. A drift report that cries about everything is a
    # drift report nobody reads.
    assert UID_B not in {d.uid for d in drifts}

    # ...and NON-BLOCKING. The whole point.
    assert report.exit_code == 0
    assert shadow.SHADOW_EXIT_CODE == 0
    assert "NON-BLOCKING" in report.render()
