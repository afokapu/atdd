# URN: test:migrate-projection-authority:plan-migration-rollout:K001-UNIT-002-exit-criteria-met-after-cutover
# Acceptance: acc:migrate-projection-authority:K001-UNIT-002-exit-criteria-met-after-cutover
# WMBT: wmbt:migrate-projection-authority:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A repo after all M8 steps — projection authoritative and canonical, no provider hot-path read, no manifest fallback — reports all three exit criteria MET and the check exits zero; and this holds against THIS repo's real source tree, not a fixture. Refs #1434.
"""The cutover check passes once, and only once, all three criteria hold (K001-UNIT-002).

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: GREEN
WMBT: wmbt:migrate-projection-authority:K001

The positive case, and it is asserted against **this repository's real source tree** rather than a
fixture — because the claim M8 makes is about the code that ships, not about a synthetic package
that could be built to pass. If a manifest reader or a GitHub hot-path read is ever reintroduced
into core, this test goes red, which is the entire reason it exists.

The projection half is exercised on a real store and a real canonical projection: an M8 that passed
on an empty projection directory would be an M8 that passed on a repo which had not started.
Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state import cutover
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import project

from ._helpers import UID_A, UID_B, control_root, memory_store

#: This repo's own `atdd` package — the source tree the claim is actually about.
CORE = Path(__file__).resolve().parents[3]

_BASE = {"slug": "alpha", "owner_actor": "dev-a", "state": "ACTIVE", "wmbts": []}


def test_k001_unit_002_exit_criteria_met_after_cutover(tmp_path) -> None:
    """All three criteria pass against the real core tree and a real canonical projection."""
    assert CORE.name == "atdd", CORE

    repo = control_root(tmp_path / "migrated")
    projection = repo / ".atdd" / "state" / "projection"
    with memory_store() as (_conn, store):
        store.objects.upsert(UID_A, WORK_ITEM_KIND, state="PLANNED", data=dict(_BASE))
        store.objects.upsert(UID_B, WORK_ITEM_KIND, state="GREEN",
                             data={**_BASE, "slug": "beta"})
        project(store, projection)

    # The manifest is gone. And — the point of Y002 — it being gone is not what makes this pass;
    # the READERS being gone is. See Y002-UNIT-002.
    assert not (repo / ".atdd" / "manifest.yaml").exists()

    report = cutover.check(repo, package=CORE)

    assert report.met, report.render()
    assert report.exit_code == 0
    assert len(report.criteria) == 3
    assert [criterion.name for criterion in report.criteria] == list(cutover.CRITERIA)
    for criterion in report.criteria:
        assert criterion.met, criterion.render()
        assert criterion.blockers == []

    rendered = report.render()
    assert "COMPLETE — all 3 exit criteria met" in rendered
    assert rendered.count("[PASS]") == 3
    assert "[FAIL]" not in rendered

    # Each criterion delegates to the guard that OWNS it — there is no second implementation here
    # that could pass while the real gate fails.
    from atdd.state import hot_path, manifest_fallback

    assert hot_path.offenders(CORE) == []
    assert manifest_fallback.offenders(CORE) == []
