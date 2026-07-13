# URN: test:enforce-merge-authority:run-merge-checks:E002-SMOKE-001-illegal-projection-rejected-end-end
# Acceptance: acc:enforce-merge-authority:E002-SMOKE-001-illegal-projection-rejected-end-end
# WMBT: wmbt:enforce-merge-authority:E002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: in a real checkout against a plain non-GitHub git remote, a branch whose projection change is canonical, schema-valid and jumps PLANNED->GREEN with no RED evidence and no ATDD-Transition trailer is rejected by the real merge-authority CLI run — non-zero, the legal-transition check naming the illegal PLANNED->GREEN and the trailer cross-check naming the missing trailer — while a legal, correctly-trailered branch exits zero. Refs #1400.
"""The illegal branch is rejected end-to-end, against a BARE remote (E002-SMOKE-001).

wagon: enforce-merge-authority | feature: run-merge-checks | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:E002

Everything the wagon claims, driven through the real ``atdd state merge-authority`` CLI in
a real checkout of a real git remote that has **no GitHub behind it** — no API, no issue
numbers, no labels, no provider. The branch under test is the adversarial one: byte-perfect
canonical, schema-valid, and a lie. It jumps ``PLANNED -> GREEN`` with no RED evidence and
says nothing about it in its trailers.

That the remote is bare is the point, not a convenience. If the run rejects this branch
against plain git object storage, then CI's authority is git's and not GitHub's — and the
gate is real wherever the repository happens to be hosted (I7, spec §4). Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes, object_digest

from ._helpers import TOKEN_DIGEST, UID_X, document
from ._live import atdd_state, branch, commit, install_policy, push, repo_on_bare_remote


def _write(repo, doc) -> None:
    out = repo / PROJECTION_RELATIVE
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))


@pytest.mark.smoke
def test_e002_smoke_001_illegal_projection_rejected_end_end(tmp_path) -> None:
    """Canonical, schema-valid, lifecycle-illegal — and the real run refuses it anyway."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    install_policy(repo)

    # main carries wi_x at PLANNED. This is the merge base every check diffs against.
    planned = document(UID_X, phase="PLANNED", body="the plan", wmbts=["wmbt:x:C001"])
    _write(repo, planned)
    commit(repo, "feat(x): plan wi_x\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 f"ATDD-Projection-Digest: {object_digest(planned)}\n")
    push(repo)

    # The illegal branch: PLANNED -> GREEN, no RED evidence, no ATDD-Transition trailer.
    branch(repo, "feat/illegal")
    green = document(UID_X, phase="GREEN", body="the plan", wmbts=["wmbt:x:C001"])
    _write(repo, green)
    commit(repo, "feat(x): straight to GREEN\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 f"ATDD-Projection-Digest: {object_digest(green)}\n")

    result = atdd_state(repo, "merge-authority", "--base", "origin/main")

    # The run exits non-zero.
    assert result.returncode == 1, result.stdout + result.stderr
    out = result.stdout

    # The legal-transition check names the illegal PLANNED->GREEN transition...
    assert "[FAIL] legal-transition" in out
    assert "PLANNED->GREEN" in out
    assert "PLANNED->RED" in out and "(skipped)" in out
    assert "failing_test_evidence" in out

    # ...and the trailer/diff cross-check names the missing ATDD-Transition trailer.
    assert "[FAIL] trailer-cross-check" in out
    assert "no ATDD-Transition trailer" in out

    # The branch was canonical and schema-valid all along — which is exactly the point.
    assert "[PASS] projection-canonicality" in out
    assert "[PASS] projection-schema" in out
    assert "[PASS] no-secrets" in out
    assert "[PASS] core-no-provider" in out   # against a bare remote, with zero providers

    # A branch whose projection change is legal and correctly trailered exits zero.
    red = document(UID_X, phase="RED", body="the plan", wmbts=["wmbt:x:C001"])
    _write(repo, red)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "test_wi_x.py").write_text(
        "def test_x() -> None:\n    raise AssertionError('RED')\n", encoding="utf-8")
    commit(repo, "test(x): the failing acceptance\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 "ATDD-Transition: PLANNED->RED\n"
                 f"ATDD-Token-Digest: {TOKEN_DIGEST}\n"
                 "ATDD-Gate: E019\n"
                 f"ATDD-Projection-Digest: {object_digest(red)}\n")

    legal = atdd_state(repo, "merge-authority", "--base", "origin/main")
    assert legal.returncode == 0, legal.stdout + legal.stderr
    assert "merge-authority run PASSED" in legal.stdout
    assert "[FAIL]" not in legal.stdout
