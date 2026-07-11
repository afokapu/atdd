# URN: test:govern-projection-fields:verify-merge-matrix:C002-SMOKE-001-merge-matrix-blind-spot
# Acceptance: acc:govern-projection-fields:C002-SMOKE-001-merge-matrix-blind-spot
# WMBT: wmbt:govern-projection-fields:C002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state merge-matrix-check` CLI in a real checkout: the committed policy's eight merge rules are exercised against all four divergence cases (32 cells), and a policy that declares a ninth rule — for which no cells exist — fails the check, naming every unexercised cell Refs #1400.
"""The matrix's completeness is checked by the real CLI (C002-SMOKE-001).

wagon: govern-projection-fields | feature: verify-merge-matrix | phase: SMOKE
WMBT: wmbt:govern-projection-fields:C002

The check that matters here is the second one. Anybody can assert a matrix is complete against
itself. This asserts it against the **committed policy** — so the moment somebody declares a
new merge rule in a real checkout, the real command starts failing in CI and keeps failing
until the four cells that exercise it exist.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.ownership import POLICY_RELATIVE

from ._helpers import policy_document
from ._live import atdd_state, repo_on_bare_remote


@pytest.mark.smoke
def test_c002_smoke_001_merge_matrix_blind_spot(tmp_path) -> None:
    """Every declared rule × case is exercised; a newly declared rule fails the check."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    complete = atdd_state(repo, "merge-matrix-check")
    assert complete.returncode == 0, complete.stdout + complete.stderr
    assert "32/32" in complete.stdout
    assert "8 rule(s) × 4 divergence case(s)" in complete.stdout

    # Declare a ninth merge rule in the REAL policy file of a real checkout. Nothing else
    # changes — and the matrix is now incomplete, because nobody has driven the new rule.
    grown = policy_document(rule={"slug": "last-writer-wins"})
    (repo / POLICY_RELATIVE).write_text(yaml.safe_dump(grown), encoding="utf-8")

    blind = atdd_state(repo, "merge-matrix-check")
    assert blind.returncode == 1
    for case in ("identical", "no-op", "evidence-backed", "unsafe"):
        assert f"last-writer-wins × {case}" in blind.stderr
    assert "unexercised" in blind.stderr
