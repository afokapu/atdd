# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-UNIT-001-absent-manifest-does-not-degrade-reads
# Acceptance: acc:migrate-projection-authority:Y002-UNIT-001-absent-manifest-does-not-degrade-reads
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: Deleting .atdd/manifest.yaml changes NO core read result — every lifecycle read (phase, train, branch, wagon, feature, slug↔issue, the whole work-item list, branch registration) returns exactly what it returned with the manifest present, and none of them raises or silently degrades. Refs #1434.
"""An absent manifest changes no read result (Y002-UNIT-001).

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: RED
WMBT: wmbt:migrate-projection-authority:Y002

The honest test of "the manifest is no longer a source of truth" is not "the file is gone" — it is
**the file's absence makes no difference**. A repo where deleting the manifest changes an answer is
a repo where the manifest was still answering.

So every core lifecycle read is exercised twice, against the identical store: once with a manifest
present (and deliberately holding *contradictory* values, so a reader that still consulted it would
return the manifest's answer and be caught), and once with it deleted. The results must be equal,
and nothing may raise. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader

from ._helpers import control_root

_ISSUE = 1434
_SLUG = "adopt-state-projection"

#: What the STORE says. The truth.
_TRUTH = {
    "phase": "GREEN",
    "train": "train:commons:spine",
    "branch": "feat/adopt-state-projection",
    "wagon": "migrate-projection-authority",
    "feature": "feature:migrate-projection-authority:decommission-manifest-fallback",
}

#: What the MANIFEST says — deliberately every value contradicted. A reader that still falls back
#: returns one of these, and is caught red-handed rather than merely suspected.
_LIES = {
    "status": "INIT",
    "train": "train:lies:0000",
    "branch": "feat/stale-and-wrong",
    "wagon": "some-other-wagon",
    "feature": "feature:lies:nope",
}


def _seed(root: Path) -> None:
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            _SLUG, WORK_ITEM_KIND, state=_TRUTH["phase"],
            data={k: v for k, v in _TRUTH.items() if k != "phase"},
        )
        store.external_refs.link(_SLUG, GITHUB_PROVIDER, "issue", str(_ISSUE), data={})
    finally:
        conn.close()


def _write_lying_manifest(root: Path) -> Path:
    path = root / ".atdd" / "manifest.yaml"
    path.write_text(
        yaml.safe_dump({"version": "2.0", "sessions": [
            {"id": str(_ISSUE), "slug": _SLUG, "issue_number": _ISSUE, **_LIES},
        ]}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _every_core_read(root: Path) -> dict:
    """Every lifecycle read a core command makes, as one snapshot."""
    from atdd.coach.commands.issue import IssueManager

    with WorkItemReader(control_root=root) as reader:
        snapshot = {
            "status": reader.status(_ISSUE),
            "train": reader.train(_ISSUE),
            "branch": reader.branch(_ISSUE),
            "wagon": reader.wagon(_ISSUE),
            "feature": reader.feature(_ISSUE),
            "issue_for_slug": reader.issue_number_for_slug(_SLUG),
            "session_entry": reader.session_entry(_ISSUE),
            "all_work_items": reader.all_work_items(),
            "issue_wagon_map": reader.issue_wagon_map(),
        }

    manager = IssueManager(root)
    snapshot["branch_is_registered"] = manager.branch_is_registered(f"feat/{_SLUG}")
    snapshot["branch_unregistered"] = manager.branch_is_registered("feat/never-heard-of-it")
    return snapshot


def test_y002_unit_001_absent_manifest_does_not_degrade_reads(tmp_path) -> None:
    """Every core read returns the same answer with the manifest present and deleted."""
    root = control_root(tmp_path / "repo")
    _seed(root)
    manifest = _write_lying_manifest(root)

    with_manifest = _every_core_read(root)

    # The reads already ignore the manifest — every value is the STORE's, not the lie beside it.
    assert with_manifest["status"] == _TRUTH["phase"]
    assert with_manifest["train"] == _TRUTH["train"]
    assert with_manifest["branch"] == _TRUTH["branch"]
    assert with_manifest["wagon"] == _TRUTH["wagon"]
    assert with_manifest["feature"] == _TRUTH["feature"]
    assert with_manifest["issue_for_slug"] == _ISSUE
    assert with_manifest["branch_is_registered"] is True
    assert with_manifest["branch_unregistered"] is False

    # Now delete it. This is the moment of truth.
    manifest.unlink()
    assert not manifest.exists()

    without_manifest = _every_core_read(root)

    # IDENTICAL. Not "still works" — identical, field for field. Nothing raised, nothing degraded
    # to None, nothing fell back to an empty list.
    assert without_manifest == with_manifest, (
        "deleting the manifest changed a core read result — it was still a source of truth"
    )
    assert without_manifest["all_work_items"], "reads degraded to empty with the manifest absent"
    assert without_manifest["session_entry"] is not None
