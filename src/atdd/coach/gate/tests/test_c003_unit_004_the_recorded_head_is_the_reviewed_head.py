# URN: test:drive-state-machine:coach-state-machine-and-runtime:C003-UNIT-004-the-recorded-head-is-the-reviewed-head
# Acceptance: acc:drive-state-machine:C003-UNIT-004-the-recorded-head-is-the-reviewed-head
# WMBT: wmbt:drive-state-machine:C003
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-004 — the commit the token names is the commit the operator saw.

#2005 Decision 2 chose the head commit partly because it is "already the unit CI
reports against". That third justification does not hold.

`mint_head._branch_head` reads the LOCAL `refs/heads/<branch>`. The operator
reviews the diff and the CI run on the PULL REQUEST, which is the REMOTE head.
Measured 2026-09-13 across all 23 open pull requests in this repository:

    resolve_issue_head returns a SHA                 14 / 14
    ...equal to the head the operator reviews        11 / 14
    ...not equal                                      3 / 14  (21%)

Of the three misses, the local ref was AHEAD by 3 commits and by 1 commit, and
one was genuinely diverged. So in two of three the mint would attest commits that
were NEVER PUSHED — CI never ran on them, the reviewer never saw them, and they
are not what merges.

That failure is silent and in the worst direction. Today the token claims no
commit at all; binding the local ref would make it claim a specific WRONG one,
with nothing printed. A manufactured attestation is worse than an absent one.

So: record the reviewed head, or refuse and say the reviewed head could not be
established. Never silently record the local ref.

RED state: no resolver returns a reviewed head, and the mint records no head.
"""
from __future__ import annotations

import subprocess

import pytest

pytestmark = [pytest.mark.platform]

_BRANCH = "feat/c003-lab"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo_with_remote(tmp_path):
    """A repo whose local branch is AHEAD of its remote by one unpushed commit.

    Returns (repo, local_sha, remote_sha). This is the measured shape: 2 of the 3
    disagreements in this repository were local-ahead, not local-stale.
    """
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "-q", "--bare")

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "lab@example.invalid")
    _git(repo, "config", "user.name", "Lab")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "f.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "checkout", "-qb", _BRANCH)
    (repo / "f.txt").write_text("reviewed on the pull request\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the commit the operator reviewed")
    _git(repo, "push", "-q", "-u", "origin", _BRANCH)
    remote_sha = _git(repo, "rev-parse", f"refs/remotes/origin/{_BRANCH}")

    # The unpushed local commit — CI never ran on it, nobody reviewed it.
    (repo / "f.txt").write_text("never pushed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "local work, not pushed")
    local_sha = _git(repo, "rev-parse", "HEAD")

    assert local_sha != remote_sha, "the lab did not create the divergence"
    return repo, local_sha, remote_sha


def test_the_local_ref_is_not_silently_recorded(repo_with_remote):
    """The mint must not attest an unpushed commit as if it were reviewed."""
    from atdd.coach.gate.mint_head import resolve_reviewed_head

    repo, local_sha, remote_sha = repo_with_remote

    binding = resolve_reviewed_head(repo, _BRANCH)

    if binding.sha is not None:
        assert binding.sha != local_sha, (
            f"the mint recorded the local ref {local_sha[:9]}, which is ahead of "
            f"the reviewed head {remote_sha[:9]} by an unpushed commit. The token "
            "would attest content CI never ran on and the reviewer never saw."
        )
        assert binding.sha == remote_sha, (
            f"the recorded head {binding.sha[:9]} is neither the reviewed head "
            f"{remote_sha[:9]} nor a refusal"
        )
    else:
        assert binding.reason, (
            "the reviewed head could not be established and the binding carries "
            "no reason; a refusal an operator cannot act on is the defect this "
            "toolkit is named for"
        )
        assert "review" in binding.reason.lower() or "push" in binding.reason.lower(), (
            f"the refusal does not say what could not be established: {binding.reason!r}"
        )


def test_an_agreeing_ref_is_recorded(repo_with_remote):
    """When local and reviewed agree, the mint records that commit and proceeds."""
    from atdd.coach.gate.mint_head import resolve_reviewed_head

    repo, _local_sha, remote_sha = repo_with_remote
    _git(repo, "push", "-q", "origin", _BRANCH)
    pushed = _git(repo, "rev-parse", "HEAD")

    binding = resolve_reviewed_head(repo, _BRANCH)

    assert binding.sha == pushed, (
        "local and remote now name the same commit and the mint still did not "
        f"record it: sha={binding.sha!r} reason={binding.reason!r}"
    )
