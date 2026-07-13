# URN: test:enforce-merge-authority:reject-history-secrets:C003-SMOKE-001-history-secret-leak
# Acceptance: acc:enforce-merge-authority:C003-SMOKE-001-history-secret-leak
# WMBT: wmbt:enforce-merge-authority:C003
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state merge-authority --check no-secrets` CLI over a real repo, a committed projection whose external_refs embeds a bearer token is rejected non-zero, the CLI's own output never echoes the credential it matched, and the same branch with the token replaced by its digest exits zero. Refs #1400.
"""history-secret-leak holds end-to-end through the real CLI (C003-SMOKE-001).

wagon: enforce-merge-authority | feature: reject-history-secrets | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C003

The one test that has to be end-to-end, because the surface it protects *is* the real
thing: a real commit, in a real repository, carrying a real-shaped credential in a
committed projection object — and the real CLI refusing it before it can reach a branch
anyone else will fetch.

The second assertion matters as much as the first: the CLI's own stdout is inspected for
the secret. A validator that prints what it matched has published it — into the CI log, on
the way to telling you not to publish it (I8). Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes

from ._helpers import UID_X, document
from ._live import atdd_state, branch, commit, push, repo_on_bare_remote

BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.QUJDREVGR0hJSktMTU5PUFFS.c2lnbmF0dXJlLXZhbHVl"
DIGEST = "sha256:" + "a1" * 32


def _write(repo, doc) -> None:
    out = repo / PROJECTION_RELATIVE
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))


@pytest.mark.smoke
def test_c003_smoke_001_history_secret_leak(tmp_path) -> None:
    """The real CLI refuses the credential — and never echoes it into its own output."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    _write(repo, document(UID_X, phase="PLANNED", body="x"))
    commit(repo, "feat(x): plan wi_x\n")
    push(repo)

    # A projection object whose external_refs embeds a live bearer token.
    branch(repo, "feat/leak")
    _write(repo, document(
        UID_X, phase="PLANNED", body="x",
        external_refs={"github": {"authorization": BEARER}},
    ))
    commit(repo, "chore(x): record the mirror ref\n")

    result = atdd_state(repo, "merge-authority", "--check", "no-secrets", "--base", "origin/main")

    # The run refuses the branch before the token can reach a shared branch.
    assert result.returncode == 1, result.stdout + result.stderr
    out = result.stdout
    assert "[FAIL] no-secrets" in out
    assert "bearer_token" in out
    assert f"{UID_X}.external_refs.github.authorization" in out
    assert "rotate the credential" in out

    # The CLI never echoes the credential it matched — not the value, not a fragment of it.
    assert BEARER not in result.stdout
    assert BEARER not in result.stderr
    assert "eyJhbGciOiJIUzI1NiJ9" not in result.stdout
    assert "<redacted:" in out

    # The same branch with the token replaced by its digest — the ONLY admissible form —
    # exits zero.
    branch(repo, "feat/digest")
    _write(repo, document(
        UID_X, phase="PLANNED", body="x",
        external_refs={"github": {"authorization_digest": DIGEST}},
    ))
    commit(repo, "chore(x): record the mirror ref by digest\n")

    clean = atdd_state(repo, "merge-authority", "--check", "no-secrets", "--base", "origin/main")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "no secrets in history" in clean.stdout
