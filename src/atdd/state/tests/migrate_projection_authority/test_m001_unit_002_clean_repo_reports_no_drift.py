# URN: test:migrate-projection-authority:compare-shadow-projection:M001-UNIT-002-clean-repo-reports-no-drift
# Acceptance: acc:migrate-projection-authority:M001-UNIT-002-clean-repo-reports-no-drift
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A repo whose committed projection is byte-identical to project(store) produces an EMPTY drift report and exits zero — so a clean shadow run is real evidence that flipping the blocking gate is safe, and not merely a check that always passes. Refs #1434.
"""A clean repo reports no drift (M001-UNIT-002).

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: GREEN
WMBT: wmbt:migrate-projection-authority:M001

The negative case is what gives the positive one meaning. A shadow check that reported drift on a
clean repo would be noise the team learned to ignore within a week — and the whole cutover plan
rests on the judgement "the drift has been zero long enough that we believe it", which is a
judgement you cannot make about an instrument that cries wolf.

It compares the **canonical bytes** — the same unit the blocking gate compares — so a clean shadow
run is evidence about the gate, not a rehearsal of a different check. Refs #1434 / #1400.
"""
from __future__ import annotations

from atdd.state import shadow
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import project

from ._helpers import UID_A, UID_B, control_root, memory_store

_BASE = {"slug": "alpha", "owner_actor": "dev-a", "state": "ACTIVE", "wmbts": []}


def test_m001_unit_002_clean_repo_reports_no_drift(tmp_path) -> None:
    """project(store) == the committed projection ⇒ an empty report, exit 0."""
    root = control_root(tmp_path / "repo")
    projection = root / ".atdd" / "state" / "projection"

    with memory_store() as (_conn, store):
        store.objects.upsert(UID_A, WORK_ITEM_KIND, state="PLANNED", data=dict(_BASE))
        store.objects.upsert(UID_B, WORK_ITEM_KIND, state="GREEN",
                             data={**_BASE, "slug": "beta"})
        result = project(store, projection)

        report = shadow.compare(store, root=root, projection_dir=projection,
                                sources=[shadow.SOURCE_COMMITTED])

        # The comparison is over the CANONICAL BYTES — the same unit the blocking gate uses.
        committed = {path.name: path.read_bytes() for path in projection.glob("*.yaml")}
        recomputed = {f"{uid}.yaml": blob for uid, blob in shadow.canonical_of(store).items()}
        assert recomputed == committed

    assert report.clean
    assert report.drifts == []
    assert report.checked == 2
    assert report.exit_code == 0
    assert "no drift" in report.render()
    assert len(result.files) == 2
