# URN: test:project-shared-state:compute-projection-digest:E003-SMOKE-001-projection-digest
# Acceptance: acc:project-shared-state:E003-SMOKE-001-projection-digest
# WMBT: wmbt:project-shared-state:E003
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — `atdd state digest` over a real store's projection is stable across runs, agrees across two independent checkouts, and moves when the state moves. Refs #1433.
"""SMOKE — projection-digest end-to-end through the real CLI (E003-SMOKE-001).

wagon: project-shared-state | feature: compute-projection-digest | phase: SMOKE
WMBT: wmbt:project-shared-state:E003

Refs #1433 / #1400.
"""
from __future__ import annotations

from ._live import atdd_state, make_checkout


def _digest(repo, out) -> str:
    result = atdd_state(repo, "digest", "--from", str(out))
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_e003_smoke_001_projection_digest(tmp_path) -> None:
    """The real CLI's digest is stable, host-independent, and change-sensitive."""
    author = make_checkout(tmp_path / "author")
    assert atdd_state(author, "init").returncode == 0
    created = atdd_state(author, "object", "create", "--slug", "feature-x",
                         "--owner", "dev-a", "--body", "digest me")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    out = tmp_path / "projection"
    assert atdd_state(author, "project", "--out", str(out)).returncode == 0
    first = _digest(author, out)
    assert first.startswith("sha256:")

    # Re-projecting the same store does not move the digest.
    assert atdd_state(author, "project", "--out", str(out)).returncode == 0
    assert _digest(author, out) == first

    # A second, independent checkout hydrating the same projection computes the
    # same digest — the stamp is over the content, not over the host.
    peer = make_checkout(tmp_path / "peer")
    assert atdd_state(peer, "init").returncode == 0
    assert atdd_state(peer, "hydrate", "--from", str(out)).returncode == 0
    peer_out = tmp_path / "peer-projection"
    assert atdd_state(peer, "project", "--out", str(peer_out)).returncode == 0
    assert _digest(peer, peer_out) == first

    # Moving the state moves the digest.
    assert atdd_state(author, "object", "rename", uid, "--slug", "feature-y").returncode == 0
    assert atdd_state(author, "project", "--out", str(out)).returncode == 0
    assert _digest(author, out) != first
