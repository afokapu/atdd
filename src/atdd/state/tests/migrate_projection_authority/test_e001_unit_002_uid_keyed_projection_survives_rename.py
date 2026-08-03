# URN: test:migrate-projection-authority:migrate-manifest-projection:E001-UNIT-002-uid-keyed-projection-survives-rename
# Acceptance: acc:migrate-projection-authority:E001-UNIT-002-uid-keyed-projection-survives-rename
# WMBT: wmbt:migrate-projection-authority:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A work item whose SLUG changes between migration runs (its uid unchanged) still projects to the same <uid>.yaml path — the new slug appears INSIDE the document, no second slug-named file is created, and the file count does not grow. Refs #1434.
"""A rename moves the slug, never the file (E001-UNIT-002).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: RED
WMBT: wmbt:migrate-projection-authority:E001

Identity is the uid; slug and title are display metadata (spec §10 rules 1–2). The test of that
sentence is a rename: if the projection path derives from the slug, renaming a work item silently
forks it into two documents, and the second developer to pull gets a corpus with one work item in
it twice. The path must not move. Refs #1434 / #1400.
"""
from __future__ import annotations

import yaml

from atdd.state.manifest_migration import migrate

from ._helpers import UID_A, control_root, entry, memory_store, projection_files, write_manifest


def test_e001_unit_002_uid_keyed_projection_survives_rename(tmp_path) -> None:
    """The slug changes, the uid does not — so the projection path does not either."""
    root = control_root(tmp_path / "repo")
    out = tmp_path / "projection"
    expected = f"{UID_A}.yaml"

    # Migrate once, under the original slug.
    write_manifest(root, [entry("original-slug", uid=UID_A, phase="PLANNED")])
    with memory_store() as (_conn, store):
        migrate(root, store=store, out_dir=out)
        assert projection_files(root, out) == [expected]
        before = (out / expected).read_bytes()
        assert b"original-slug" in before

        # Now rename it: the slug changes, the uid does not. This is the whole scenario.
        write_manifest(root, [entry("renamed-slug", uid=UID_A, phase="PLANNED")])
        migrate(root, store=store, out_dir=out)

    # The path is unchanged, because it derives from the uid.
    assert projection_files(root, out) == [expected], (
        "a rename must not create a second projection file"
    )
    # No slug-named file appeared — under either name.
    assert not (out / "original-slug.yaml").exists()
    assert not (out / "renamed-slug.yaml").exists()

    # The rename landed INSIDE the document, which is where display metadata belongs.
    document = yaml.safe_load((out / expected).read_text(encoding="utf-8"))
    assert document["uid"] == UID_A
    assert document["slug"] == "renamed-slug"
