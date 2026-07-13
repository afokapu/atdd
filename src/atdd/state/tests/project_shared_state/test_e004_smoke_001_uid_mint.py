# URN: test:project-shared-state:mint-object-identity:E004-SMOKE-001-uid-mint
# Acceptance: acc:project-shared-state:E004-SMOKE-001-uid-mint
# WMBT: wmbt:project-shared-state:E004
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state object create` CLI mints a unique immutable wi_ uid into a real store, and that uid alone names the projection file. Refs #1433.
"""SMOKE — uid-mint end-to-end through the real CLI (E004-SMOKE-001).

wagon: project-shared-state | feature: mint-object-identity | phase: SMOKE
WMBT: wmbt:project-shared-state:E004

Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.identity import UID_RE

from ._live import atdd_state, make_checkout


def test_e004_smoke_001_uid_mint(tmp_path) -> None:
    """The real CLI mints distinct wi_ uids for same-slug creates and names files by uid."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    first = atdd_state(repo, "object", "create", "--slug", "feature-x", "--owner", "dev-a")
    second = atdd_state(repo, "object", "create", "--slug", "feature-x", "--owner", "dev-a")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    uid_one, uid_two = first.stdout.strip(), second.stdout.strip()
    assert uid_one != uid_two
    assert UID_RE.match(uid_one), uid_one
    assert UID_RE.match(uid_two), uid_two

    projected = atdd_state(repo, "project", "--out", str(tmp_path / "projection"))
    assert projected.returncode == 0, projected.stderr
    names = sorted(p.name for p in (tmp_path / "projection").glob("*.yaml"))
    assert names == sorted([f"{uid_one}.yaml", f"{uid_two}.yaml"])
