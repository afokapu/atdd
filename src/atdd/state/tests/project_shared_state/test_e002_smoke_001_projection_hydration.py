# URN: test:project-shared-state:hydrate-projection:E002-SMOKE-001-projection-hydration
# Acceptance: acc:project-shared-state:E002-SMOKE-001-projection-hydration
# WMBT: wmbt:project-shared-state:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — a committed projection hydrates through the real CLI into a FRESH real state.sqlite in a second checkout, and re-projects to the same bytes. Refs #1433.
"""SMOKE — projection-hydration end-to-end through the real CLI (E002-SMOKE-001).

wagon: project-shared-state | feature: hydrate-projection | phase: SMOKE
WMBT: wmbt:project-shared-state:E002

This is the collaboration claim in miniature: Dev A's committed projection, carried
by nothing but files on disk, rebuilds Dev B's store — no GitHub, no shared SQLite.
Refs #1433 / #1400.
"""
from __future__ import annotations

from ._live import atdd_state, make_checkout


def test_e002_smoke_001_projection_hydration(tmp_path) -> None:
    """A projection written by one real store hydrates into another and re-projects identically."""
    author = make_checkout(tmp_path / "author")
    assert atdd_state(author, "init").returncode == 0
    created = atdd_state(author, "object", "create", "--slug", "feature-x",
                         "--owner", "dev-a", "--body", "shared through git alone")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    shared = tmp_path / "shared-projection"
    assert atdd_state(author, "project", "--out", str(shared)).returncode == 0
    author_bytes = (shared / f"{uid}.yaml").read_bytes()

    # A SECOND real checkout, with its own fresh state.sqlite and no store to copy.
    peer = make_checkout(tmp_path / "peer")
    assert atdd_state(peer, "init").returncode == 0
    assert not (peer / ".atdd" / "state" / "projection").exists()

    hydrated = atdd_state(peer, "hydrate", "--from", str(shared))
    assert hydrated.returncode == 0, hydrated.stderr
    assert uid in hydrated.stdout

    # The peer's store now re-projects to exactly the bytes the author committed.
    peer_out = tmp_path / "peer-projection"
    assert atdd_state(peer, "project", "--out", str(peer_out)).returncode == 0
    assert (peer_out / f"{uid}.yaml").read_bytes() == author_bytes
