# URN: test:enforce-merge-authority:validate-transition-legality:C001-SMOKE-001-illegal-transition-merge
# Acceptance: acc:enforce-merge-authority:C001-SMOKE-001-illegal-transition-merge
# WMBT: wmbt:enforce-merge-authority:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end against a real checkout and the real `atdd state merge-authority --check legal-transition` CLI, a canonical projection carrying a backward GREEN->RED move and an unevidenced PLANNED->GREEN jump is rejected non-zero, while the same objects walking the ladder with their evidence exit zero — no mocks, no manual patching. Refs #1400.
"""illegal-transition-merge holds end-to-end through the real CLI (C001-SMOKE-001).

wagon: enforce-merge-authority | feature: validate-transition-legality | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:C001

The load-bearing gate, driven as CI drives it: the installed command, a real repository, a
real merge base, and a projection that every other check admits. Two ways to be illegal are
exercised at once — a *backward* move (which no evidence can rescue) and an *unevidenced
skip* (which evidence would) — because the difference between them is the whole content of
the §6 model, and a gate that conflated the two would be no gate at all. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes, object_digest

from ._helpers import TOKEN_DIGEST, UID_X, UID_Y, document
from ._live import atdd_state, branch, commit, push, repo_on_bare_remote


def _write(repo, *docs) -> None:
    out = repo / PROJECTION_RELATIVE
    out.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))


@pytest.mark.smoke
def test_c001_smoke_001_illegal_transition_merge(tmp_path) -> None:
    """The real CLI rejects the backward move and the unevidenced jump, and admits the walk."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    base_x = document(UID_X, phase="GREEN", body="x", wmbts=["wmbt:x:C001"])
    base_y = document(UID_Y, phase="PLANNED", body="y", wmbts=["wmbt:y:C001"])
    _write(repo, base_x, base_y)
    commit(repo, "feat: seed two objects\n")
    push(repo)

    # The illegal branch: wi_x walks BACKWARD, wi_y jumps with no evidence for what it skipped.
    branch(repo, "feat/illegal")
    _write(
        repo,
        document(UID_X, phase="RED", body="x", wmbts=["wmbt:x:C001"]),      # GREEN -> RED
        document(UID_Y, phase="GREEN", body="y", wmbts=["wmbt:y:C001"]),    # PLANNED -> GREEN
    )
    commit(repo, "feat: rewrite history the wrong way\n")

    result = atdd_state(repo, "merge-authority", "--check", "legal-transition",
                        "--base", "origin/main")

    assert result.returncode == 1, result.stdout + result.stderr
    out = result.stdout

    # The backward move is rejected as non-monotonic, and no evidence would have saved it.
    assert f"{UID_X}: GREEN->RED rejected [non_monotonic]" in out
    assert "monotonic" in out

    # The unevidenced jump is rejected naming the gate it skipped and what it never carried.
    assert f"{UID_Y}: PLANNED->GREEN rejected [skipped_gate]" in out
    assert "PLANNED->RED (skipped)" in out
    assert "operator_token_digest" in out

    # The same objects walking the ladder WITH their evidence exit zero.
    branch(repo, "feat/legal")
    _write(
        repo,
        base_x,  # wi_x stays where it is
        document(UID_Y, phase="RED", body="y", wmbts=["wmbt:y:C001"]),
    )
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_wi_y.py").write_text(
        "def test_y() -> None:\n    raise AssertionError('RED')\n", encoding="utf-8")
    commit(repo, "test(y): the failing acceptance\n\n"
                 f"ATDD-Object: {UID_Y}\n"
                 "ATDD-Transition: PLANNED->RED\n"
                 f"ATDD-Token-Digest: {TOKEN_DIGEST}\n"
                 "ATDD-Gate: E019\n"
                 f"ATDD-Projection-Digest: "
                 f"{object_digest(document(UID_Y, phase='RED', body='y', wmbts=['wmbt:y:C001']))}\n")

    legal = atdd_state(repo, "merge-authority", "--check", "legal-transition",
                       "--base", "origin/main")
    assert legal.returncode == 0, legal.stdout + legal.stderr
    assert "every transition is lifecycle-legal" in legal.stdout
