# URN: test:migrate-projection-authority:migrate-manifest-projection:E001-UNIT-001-emits-one-projection-per-work-item
# Acceptance: acc:migrate-projection-authority:E001-UNIT-001-emits-one-projection-per-work-item
# WMBT: wmbt:migrate-projection-authority:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A manifest of N work items migrates to exactly N files under .atdd/state/projection/, every one named <uid>.yaml and never <slug>.yaml, and a second run reproduces them byte-identically (invariant I1). Refs #1434.
"""One deterministic projection file per work item, keyed by uid (E001-UNIT-001).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: GREEN
WMBT: wmbt:migrate-projection-authority:E001

The legacy manifest keys work items by **slug** — display metadata, and mutable. The projection
keys them by **uid** — minted once, never reused. This is the step that crosses that gap, and the
two properties it must have are that it crosses it *completely* (one file per work item, none
missing, none doubled) and *reproducibly* (I1: the same logical store yields the same bytes on
every host and every run). Refs #1434 / #1400.
"""
from __future__ import annotations

from atdd.state.manifest_migration import migrate

from ._helpers import (
    UID_A, UID_B, UID_C, control_root, healthy_sessions, memory_store, projection_files,
    write_manifest,
)


def test_e001_unit_001_emits_one_projection_per_work_item(tmp_path) -> None:
    """N work items → N <uid>.yaml files; a second run is byte-identical."""
    root = control_root(tmp_path / "repo")
    write_manifest(root, healthy_sessions())
    out = tmp_path / "projection"

    with memory_store() as (_conn, store):
        report = migrate(root, store=store, out_dir=out)

        # Exactly one file per work item — no more (a duplicate) and no fewer (a drop).
        assert report.migrated == 3
        assert projection_files(root, out) == sorted(
            f"{uid}.yaml" for uid in (UID_A, UID_B, UID_C)
        )

        # Every file is named by the UID. Not one is named by the slug — which is the whole point,
        # and the thing a lazy implementation gets wrong while still passing a count check.
        names = set(projection_files(root, out))
        for slug in ("alpha", "beta", "gamma"):
            assert f"{slug}.yaml" not in names

        first = {path.name: path.read_bytes() for path in out.glob("*.yaml")}

        # I1: run it again and the bytes do not move.
        second_dir = tmp_path / "projection-again"
        migrate(root, store=store, out_dir=second_dir)

    second = {path.name: path.read_bytes() for path in second_dir.glob("*.yaml")}
    assert second == first, "a second migration of the same manifest must be byte-identical (I1)"

    # The digest is over the content, so it moves with the content and not with the run.
    assert report.digest.startswith("sha256:")
