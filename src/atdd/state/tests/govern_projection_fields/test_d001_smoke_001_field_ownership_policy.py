# URN: test:govern-projection-fields:define-field-ownership:D001-SMOKE-001-field-ownership-policy
# Acceptance: acc:govern-projection-fields:D001-SMOKE-001-field-ownership-policy
# WMBT: wmbt:govern-projection-fields:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end in a real checkout: a repo with no committed field-ownership policy fails the real CLI check with PolicyNotFound naming the expected path .atdd/policy/field-ownership.yaml, and with the shipped policy committed the same command resolves all 13 projection schema fields to a declared writer and merge rule Refs #1400.
"""The policy is a committed file, and its absence is loud (D001-SMOKE-001).

wagon: govern-projection-fields | feature: define-field-ownership | phase: SMOKE
WMBT: wmbt:govern-projection-fields:D001

A real checkout, the real CLI, and the two states a repository can be in. Without the policy
the command refuses and says where the file belongs; with it, every projection field resolves
to a declared writer. What must never happen — and what this pins — is the middle state: a
command that passes cheerfully over a repository that has declared nothing.
"""
from __future__ import annotations

import pytest

from atdd.state.ownership import POLICY_RELATIVE

from ._live import atdd_state, install_policy, repo_on_bare_remote


@pytest.mark.smoke
def test_d001_smoke_001_field_ownership_policy(tmp_path) -> None:
    """No policy: refused, naming the path. Policy committed: every field resolves."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    # Take the policy away — the state a repository is in before this wagon lands.
    (repo / POLICY_RELATIVE).unlink()

    missing = atdd_state(repo, "ownership-check")
    assert missing.returncode == 1, "an undeclared policy is not an empty one"
    assert str(POLICY_RELATIVE) in missing.stderr
    assert "field-ownership.yaml" in missing.stderr

    # The merge driver refuses to run without it too: judging a merge with no ownership table
    # would mean auto-merging fields nobody owns.
    ours = repo / "ours.yaml"
    ours.write_text("uid: wi_01HF7YAT00M78607F0000000X1\nphase: INIT\n", encoding="utf-8")
    driverless = atdd_state(repo, "merge-projection", "--ours", str(ours), "--theirs", str(ours))
    assert driverless.returncode == 1
    assert "field-ownership" in driverless.stderr

    # Put the shipped policy back: the same command now resolves every field, as data.
    install_policy(repo)
    resolved = atdd_state(repo, "ownership-check")
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    assert "13 field(s)" in resolved.stdout
