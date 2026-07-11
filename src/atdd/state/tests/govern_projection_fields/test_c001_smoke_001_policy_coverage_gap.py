# URN: test:govern-projection-fields:define-field-ownership:C001-SMOKE-001-policy-coverage-gap
# Acceptance: acc:govern-projection-fields:C001-SMOKE-001-policy-coverage-gap
# WMBT: wmbt:govern-projection-fields:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state ownership-check` CLI in a real checkout of a real bare remote: the shipped policy is accepted, a policy omitting a projection field exits non-zero naming the uncovered field, and a policy naming the actor 'human' as the writer of phase exits non-zero naming the field and the unknown writer Refs #1400.
"""The coverage gap is caught by the real CLI, in a real checkout (C001-SMOKE-001).

wagon: govern-projection-fields | feature: define-field-ownership | phase: SMOKE
WMBT: wmbt:govern-projection-fields:C001

The policy under test is the one this repository actually commits — copied into the checkout,
not re-typed by a fixture — and the checker is the real command, run as CI runs it. A policy
that only exists inside a test proves nothing about the branch a merge lands on.
"""
from __future__ import annotations

import pytest
import yaml

from ._helpers import policy_document
from ._live import atdd_state, repo_on_bare_remote


@pytest.mark.smoke
def test_c001_smoke_001_policy_coverage_gap(tmp_path) -> None:
    """The shipped policy passes; a gap and an unknown writer each fail, by name."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    # The policy the repo commits, checked by the real command: accepted.
    shipped = atdd_state(repo, "ownership-check")
    assert shipped.returncode == 0, shipped.stdout + shipped.stderr
    assert "every projection field resolves to one declared writer" in shipped.stdout

    # A policy with a hole in it: refused, and the report names the uncovered field.
    gapped = tmp_path / "gapped.yaml"
    gapped.write_text(yaml.safe_dump(policy_document(omit="body")), encoding="utf-8")
    result = atdd_state(repo, "ownership-check", "--policy", str(gapped))
    assert result.returncode == 1
    assert "body" in result.stderr
    assert "uncovered" in result.stderr

    # A policy naming an ACTOR where a writer belongs: refused, naming the field and the actor.
    aliened = tmp_path / "human.yaml"
    aliened.write_text(
        yaml.safe_dump(policy_document(writer={"phase": "human"})), encoding="utf-8")
    unknown = atdd_state(repo, "ownership-check", "--policy", str(aliened))
    assert unknown.returncode == 1
    assert "phase" in unknown.stderr
    assert "human" in unknown.stderr

    # Neither refusal is a crash: the good policy still passes afterwards, from the same repo.
    assert atdd_state(repo, "ownership-check").returncode == 0
