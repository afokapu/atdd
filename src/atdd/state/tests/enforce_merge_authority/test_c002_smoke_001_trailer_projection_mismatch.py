# URN: test:enforce-merge-authority:verify-trailer-diff:C002-SMOKE-001-trailer-projection-mismatch
# Acceptance: acc:enforce-merge-authority:C002-SMOKE-001-trailer-projection-mismatch
# WMBT: wmbt:enforce-merge-authority:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state merge-authority --check trailer-cross-check` CLI over a real repo, a commit whose ATDD-Transition trailer disagrees with the phase its projection actually moved, and whose ATDD-Projection-Digest disagrees with the bytes it committed, is rejected non-zero naming both sides of each disagreement; the honest commit exits zero. Refs #1400.
"""trailer-projection-mismatch holds end-to-end through the real CLI (C002-SMOKE-001).

wagon: enforce-merge-authority | feature: verify-trailer-diff | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C002

The event log is only an event log if it is bound to the state it claims to describe.
Driven end-to-end: a real commit, in a real repository, whose trailers say one thing while
its projection did another — the transition it declares never happened, and the digest it
pins is not the digest of what it committed.

Both are the kind of fault that no other check in the set can see. Canonicality is happy,
the schema is happy, the transition itself is legal. Only the cross-check notices that the
audit trail has started lying. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes, object_digest

from ._helpers import TOKEN_DIGEST, UID_X, document
from ._live import atdd_state, branch, commit, push, repo_on_bare_remote

WRONG_DIGEST = "sha256:" + "ff" * 32


def _write(repo, doc) -> None:
    out = repo / PROJECTION_RELATIVE
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))


@pytest.mark.smoke
def test_c002_smoke_001_trailer_projection_mismatch(tmp_path) -> None:
    """The real CLI names both sides of the transition and digest disagreements."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    planned = document(UID_X, phase="PLANNED", body="x", wmbts=["wmbt:x:C001"])
    _write(repo, planned)
    commit(repo, "feat(x): plan wi_x\n")
    push(repo)

    # A commit whose trailers disagree with the diff on the transition AND on the digest.
    branch(repo, "feat/mismatch")
    red = document(UID_X, phase="RED", body="x", wmbts=["wmbt:x:C001"])
    _write(repo, red)
    commit(repo, "test(x): the failing acceptance\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 "ATDD-Transition: RED->GREEN\n"          # the projection moved PLANNED->RED
                 f"ATDD-Token-Digest: {TOKEN_DIGEST}\n"
                 "ATDD-Gate: E019\n"
                 f"ATDD-Projection-Digest: {WRONG_DIGEST}\n")   # not the bytes it committed

    result = atdd_state(repo, "merge-authority", "--check", "trailer-cross-check",
                        "--base", "origin/main")

    assert result.returncode == 1, result.stdout + result.stderr
    out = result.stdout

    # The transition disagreement names BOTH sides: what the log claims, what happened.
    assert "transition disagreement" in out
    assert "'RED->GREEN'" in out
    assert "'PLANNED->RED'" in out

    # The digest disagreement names both digests too.
    assert "projection_digest disagreement" in out
    assert WRONG_DIGEST in out
    assert object_digest(red) in out
    assert UID_X in out

    # The honest commit — same diff, trailers that tell the truth — exits zero.
    branch(repo, "feat/honest")
    commit(repo, "test(x): the failing acceptance\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 "ATDD-Transition: PLANNED->RED\n"
                 f"ATDD-Token-Digest: {TOKEN_DIGEST}\n"
                 "ATDD-Gate: E019\n"
                 f"ATDD-Projection-Digest: {object_digest(red)}\n")

    honest = atdd_state(repo, "merge-authority", "--check", "trailer-cross-check",
                        "--base", "origin/main")
    assert honest.returncode == 0, honest.stdout + honest.stderr
    assert "trailers match the projection diff" in honest.stdout
