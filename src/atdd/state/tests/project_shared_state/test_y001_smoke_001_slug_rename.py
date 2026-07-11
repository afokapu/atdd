# URN: test:project-shared-state:mint-object-identity:Y001-SMOKE-001-slug-rename
# Acceptance: acc:project-shared-state:Y001-SMOKE-001-slug-rename
# WMBT: wmbt:project-shared-state:Y001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — `atdd state object rename` against a real store leaves the uid and the <uid>.yaml filename untouched while the document's slug and the projection digest move. Refs #1433.
"""SMOKE — slug-rename end-to-end through the real CLI (Y001-SMOKE-001).

wagon: project-shared-state | feature: mint-object-identity | phase: SMOKE
WMBT: wmbt:project-shared-state:Y001

Refs #1433 / #1400.
"""
from __future__ import annotations

import yaml

from ._live import atdd_state, make_checkout


def test_y001_smoke_001_slug_rename(tmp_path) -> None:
    """The real CLI renames display metadata without moving identity or the file."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "feature-x", "--owner", "dev-a")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    out = tmp_path / "projection"
    assert atdd_state(repo, "project", "--out", str(out)).returncode == 0
    before_digest = atdd_state(repo, "digest", "--from", str(out)).stdout.strip()

    renamed = atdd_state(repo, "object", "rename", uid, "--slug", "feature-y")
    assert renamed.returncode == 0, renamed.stderr
    assert atdd_state(repo, "project", "--out", str(out)).returncode == 0

    # Still exactly one file, still named for the uid; the slug moved inside it.
    assert [p.name for p in sorted(out.glob("*.yaml"))] == [f"{uid}.yaml"]
    document = yaml.safe_load((out / f"{uid}.yaml").read_text(encoding="utf-8"))
    assert document["uid"] == uid
    assert document["slug"] == "feature-y"

    # The digest moved, proving the rename reached the shared projection.
    after_digest = atdd_state(repo, "digest", "--from", str(out)).stdout.strip()
    assert after_digest.startswith("sha256:")
    assert after_digest != before_digest
