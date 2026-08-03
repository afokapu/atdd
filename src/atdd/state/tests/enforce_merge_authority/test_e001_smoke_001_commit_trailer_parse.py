# URN: test:enforce-merge-authority:parse-commit-trailer:E001-SMOKE-001-commit-trailer-parse
# Acceptance: acc:enforce-merge-authority:E001-SMOKE-001-commit-trailer-parse
# WMBT: wmbt:enforce-merge-authority:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state trailers` CLI over real commits in a real repo, a grouped multi-object commit yields one typed group per ATDD-Object and a squash merge yields its summary trailers; two runs over the same commit print byte-identical output; and a malformed block is refused rather than half-parsed. Refs #1400.
"""commit-trailer-parse holds end-to-end through the real CLI (E001-SMOKE-001).

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:E001

Real commits, made by real ``git commit``, read back by the real command. That matters more
than it sounds: git's own message handling — the blank lines it preserves, the trailing
newline it adds — is part of the input the parser has to survive, and a parser tested only
against Python string literals has not met it.

Both awkward shapes are here: the grouped multi-object commit, and the squash merge whose
individual commits are gone and whose event semantics survive only in its summary artifact.
And determinism, checked the way it actually matters — two runs, byte-identical stdout. Refs #1400.
"""
from __future__ import annotations

import pytest
import yaml

from ._helpers import TOKEN_DIGEST, UID_X, UID_Y
from ._live import atdd_state, commit, repo_on_bare_remote

DIGEST_X = "sha256:" + "b2" * 32
DIGEST_Y = "sha256:" + "c3" * 32
SUMMARY_DIGEST = "sha256:" + "d4" * 32


@pytest.mark.smoke
def test_e001_smoke_001_commit_trailer_parse(tmp_path) -> None:
    """Grouped and squash commits parse into typed groups, deterministically, from real git."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    # A real multi-object commit carrying GROUPED trailers, one group per object.
    grouped_sha = commit(repo, "feat(x,y): move two objects at once\n\n"
                               f"ATDD-Object: {UID_X}\n"
                               "ATDD-Transition: PLANNED->RED\n"
                               f"ATDD-Token-Digest: {TOKEN_DIGEST}\n"
                               "ATDD-Gate: E019\n"
                               f"ATDD-Projection-Digest: {DIGEST_X}\n"
                               "\n"
                               f"ATDD-Object: {UID_Y}\n"
                               "ATDD-Transition: RED->GREEN\n"
                               f"ATDD-Projection-Digest: {DIGEST_Y}\n")

    result = atdd_state(repo, "trailers", "--commit", grouped_sha)
    assert result.returncode == 0, result.stdout + result.stderr

    document = yaml.safe_load(result.stdout)
    assert document["commit_kind"] == "multi_object"
    # ONE trailer group per ATDD-Object — which is what lets the cross-check bind each
    # object to its own diff, rather than to the commit as an undifferentiated blob.
    assert [group["ATDD-Object"] for group in document["groups"]] == [UID_X, UID_Y]
    assert document["groups"][0]["ATDD-Projection-Digest"] == DIGEST_X
    assert document["groups"][1]["ATDD-Projection-Digest"] == DIGEST_Y
    assert document["groups"][1]["ATDD-Transition"] == "RED->GREEN"
    assert "ATDD-Token-Digest" not in document["groups"][1]  # trailers do not leak across groups

    # A real squash merge, carrying its event semantics in the summary artifact.
    squash_sha = commit(repo, "feat(x): squash-merge the branch (#1400)\n\n"
                              f"ATDD-Object: {UID_X}\n"
                              "ATDD-Transition: RED->GREEN\n"
                              f"ATDD-Projection-Digest: {DIGEST_X}\n"
                              "ATDD-Summary: .atdd/events/9f2c1b7.json\n"
                              f"ATDD-Summary-Digest: {SUMMARY_DIGEST}\n")

    squash = atdd_state(repo, "trailers", "--commit", squash_sha)
    assert squash.returncode == 0, squash.stdout + squash.stderr
    document = yaml.safe_load(squash.stdout)
    assert document["commit_kind"] == "squash_merge"
    assert document["ATDD-Summary"] == ".atdd/events/9f2c1b7.json"
    assert document["ATDD-Summary-Digest"] == SUMMARY_DIGEST

    # Two runs over the same commit return byte-identical output. CI parses this message,
    # and so does the local hook, and so will whoever audits the branch next year; if the
    # three disagree, the event log is not a log.
    again = atdd_state(repo, "trailers", "--commit", grouped_sha)
    assert again.stdout == result.stdout

    # A malformed block is refused, not half-parsed: the parser prints nothing to trust.
    bad_sha = commit(repo, "feat(x): broken trailers\n\n"
                           f"ATDD-Object: {UID_X}\n"
                           f"ATDD-Object: {UID_X}\n"
                           "ATDD-Token-Digest: ghp_A1b2C3d4E5f6G7h8I9j0K1L2M3\n")
    bad = atdd_state(repo, "trailers", "--commit", bad_sha)
    assert bad.returncode == 1
    assert "duplicate ATDD-Object" in bad.stdout
    assert "ATDD-Token-Digest is not a sha256:<hex> digest" in bad.stdout
    assert "commit_kind" not in bad.stdout  # no half-parsed group came back at all
    # ...and the refusal never echoes the raw token it refused (I8).
    assert "ghp_A1b2C3d4E5f6G7h8I9j0K1L2M3" not in bad.stdout
