# URN: test:govern-projection-fields:merge-projection-objects:R001-SMOKE-001-unsafe-merge-conflict
# Acceptance: acc:govern-projection-fields:R001-SMOKE-001-unsafe-merge-conflict
# WMBT: wmbt:govern-projection-fields:R001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: a real `git merge` where both branches rewrote the same object's body conflicts by design: git exits non-zero, the driver's report on stderr names the field body, both sides' writers and the conflict-unless-single-owner rule, the file is left unmerged in the worktree rather than resolved by picking a winner, and an unevidenced phase advance is refused the same way Refs #1400.
"""The unsafe merge conflicts, loudly and usefully (R001-SMOKE-001).

wagon: govern-projection-fields | feature: merge-projection-objects | phase: SMOKE
WMBT: wmbt:govern-projection-fields:R001

The conflict is the *feature*. Two people rewrote one body; there is no rule that combines two
prose rewrites and no honest way to pick one, so the merge stops — and what it says while
stopping is the whole value: the field, the writer on each side, and the rule that refused.

The second half is the one the model would quietly die without: a phase advance with no
evidence for the gate it skipped conflicts too, in a real git merge, rather than being
resolved by taking the further phase.
"""
from __future__ import annotations

import pytest

from atdd.state.ownership import RULE_MONOTONIC_GATED, RULE_SINGLE_OWNER
from atdd.state.projection import canonical_bytes

from ._helpers import UID_X, document
from ._live import (
    branch,
    checkout_branch,
    commit,
    git,
    merge,
    projection_file,
    repo_on_bare_remote,
)


@pytest.mark.smoke
def test_r001_smoke_001_unsafe_merge_conflict(tmp_path) -> None:
    """Both unsafe divergences conflict in a real merge, with a report naming everything."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    base = document(phase="PLANNED", body="the original body", owner_actor="dev-a")
    projection_file(repo, UID_X).write_bytes(canonical_bytes(base))
    commit(repo, "feat: shared object")

    # Two writers, one body.
    branch(repo, "dev-b")
    projection_file(repo, UID_X).write_bytes(
        canonical_bytes({**base, "body": "B's rewrite", "owner_actor": "dev-b"}))
    commit(repo, "feat: B rewrites the body")

    checkout_branch(repo, "main")
    ours = {**base, "body": "A's rewrite"}
    projection_file(repo, UID_X).write_bytes(canonical_bytes(ours))
    commit(repo, "feat: A rewrites the body")

    conflicted = merge(repo, "dev-b")

    # git stopped, and it stopped because our driver told it to.
    assert conflicted.returncode != 0
    report = conflicted.stdout + conflicted.stderr
    assert "CONFLICT" in report
    for fragment in ("body", "dev-a", "dev-b", RULE_SINGLE_OWNER):
        assert fragment in report, f"the operator is never told: {fragment}"

    # No winner was picked: the file still holds OUR version, and git has it as unmerged.
    assert projection_file(repo, UID_X).read_bytes() == canonical_bytes(ours)
    assert "UU" in git(repo, "status", "--short").stdout

    git(repo, "merge", "--abort")

    # And the phase divergence with no evidence for the skipped gate: the same refusal, in a
    # real merge, rather than a silent promotion to the further phase.
    branch(repo, "dev-c")
    projection_file(repo, UID_X).write_bytes(canonical_bytes({**base, "phase": "GREEN"}))
    commit(repo, "feat: straight to GREEN, with nothing to show for it")

    checkout_branch(repo, "main")
    projection_file(repo, UID_X).write_bytes(canonical_bytes({**base, "phase": "RED"}))
    commit(repo, "feat: PLANNED->RED")

    unevidenced = merge(repo, "dev-c")
    assert unevidenced.returncode != 0
    phase_report = unevidenced.stdout + unevidenced.stderr
    assert RULE_MONOTONIC_GATED in phase_report
    assert "no evidence" in phase_report
    assert "PLANNED->RED" in phase_report, "it names the gate that was skipped"

    # The further phase did NOT win: ours is untouched on disk.
    assert b"phase: RED" in projection_file(repo, UID_X).read_bytes()
