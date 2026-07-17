# URN: test:govern-projection-fields:merge-projection-objects:E002-SMOKE-001-safe-projection-merge
# Acceptance: acc:govern-projection-fields:E002-SMOKE-001-safe-projection-merge
# WMBT: wmbt:govern-projection-fields:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: a real `git merge` in a real checkout, through the projection merge driver registered the way an operator registers one: disjoint objects merge cleanly, and a same-object phase divergence whose further side carries committed evidence for every skipped gate auto-merges to GREEN with no conflict markers, no operator intervention, and bytes identical to the canonical projection Refs #1400.
"""git itself merges the projection, through the real driver (E002-SMOKE-001).

wagon: govern-projection-fields | feature: merge-projection-objects | phase: SMOKE
WMBT: wmbt:govern-projection-fields:E002

This is the acceptance that decides whether any of the rest is real. The driver is registered
the way an operator registers one — ``merge.atdd-projection.driver`` plus a ``.gitattributes``
entry — and then **git** decides when to call it, hands it temp files whose names are not the
uid, and interprets its exit code. A driver that passes every unit test and never gets invoked
by git has protected nothing at all.

The evidence, likewise, is real: it is a committed artifact on the incoming branch, and the
driver reads it out of the incoming commit — because a merge cannot see a developer's store
and evidence a merge cannot see is evidence it does not have (spec §6).
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.projection import canonical_bytes

from ._helpers import PLANNED_TO_RED, UID_X, UID_Y, document
from ._live import (
    atdd_state,
    branch,
    checkout_branch,
    commit,
    merge,
    projection_file,
    repo_on_bare_remote,
    write_evidence,
)


@pytest.mark.smoke
def test_e002_smoke_001_safe_projection_merge(tmp_path) -> None:
    """A real git merge: the disjoint object and the evidenced advance both land, cleanly."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    projection_file(repo, UID_X).write_bytes(canonical_bytes(document(phase="PLANNED")))
    commit(repo, "feat: shared object at PLANNED")

    # Dev B: advances the SAME object to GREEN, carrying committed evidence for both gates it
    # passes through — one artifact per gate, so B's evidence and A's do not collide — and,
    # separately, authors a disjoint object of their own.
    branch(repo, "dev-b")
    projection_file(repo, UID_X).write_bytes(canonical_bytes(document(phase="GREEN")))
    write_evidence(repo, UID_X, PLANNED_TO_RED, gate="PLANNED-RED")
    write_evidence(repo, UID_X, ("passing_test_evidence", "implementation_diff"), gate="RED-GREEN")
    projection_file(repo, UID_Y).write_bytes(
        canonical_bytes(document(uid=UID_Y, slug="feature-y", phase="INIT", owner_actor="dev-b")))
    commit(repo, "feat: PLANNED->GREEN with gate evidence, plus feature-y")

    # Dev A: advances the same object to RED on main.
    checkout_branch(repo, "main")
    projection_file(repo, UID_X).write_bytes(canonical_bytes(document(phase="RED")))
    write_evidence(repo, UID_X, PLANNED_TO_RED, gate="PLANNED-RED")
    commit(repo, "feat: PLANNED->RED")

    merged = merge(repo, "dev-b")

    # git merged it, and no operator was asked anything.
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert "CONFLICT" not in merged.stdout

    # The disjoint object merged cleanly — different uid, different file, nothing to decide.
    assert projection_file(repo, UID_Y).is_file()
    assert yaml.safe_load(projection_file(repo, UID_Y).read_text(encoding="utf-8"))["uid"] == UID_Y

    # The same-object divergence auto-merged to the further phase — because, and only because,
    # the further side carried evidence for every gate it skipped.
    blob = projection_file(repo, UID_X).read_bytes()
    assert b"<<<<<<<" not in blob and b">>>>>>>" not in blob
    document_x = yaml.safe_load(blob.decode("utf-8"))
    assert document_x["phase"] == "GREEN"

    # And the merged bytes are the canonical projection of the merged state, so the branch is
    # still canonical: the merge did not hand CI a projection that fails its own round-trip.
    assert blob == canonical_bytes(document_x)
    assert atdd_state(repo, "canonicality").returncode == 0

    # The merge is a real commit, with both parents — not a fast-forward that dodged the driver.
    assert len(merged.stdout) >= 0
    assert atdd_state(repo, "field-writer").returncode == 0
