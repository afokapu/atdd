# URN: test:enforce-merge-authority:parse-commit-trailer:D001-SMOKE-001-commit-trailer-schema
# Acceptance: acc:enforce-merge-authority:D001-SMOKE-001-commit-trailer-schema
# WMBT: wmbt:enforce-merge-authority:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end through the real `atdd state trailers` CLI over a real repo, a commit carrying an ungrammatical ATDD-Transition and an unknown ATDD-* trailer is refused non-zero naming both offending trailer keys, while the canonical section-5 group parses and prints as a schema-valid typed document. Refs #1400.
"""commit-trailer-schema holds end-to-end through the real CLI (D001-SMOKE-001).

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: SMOKE
WMBT: wmbt:enforce-merge-authority:D001

The schema is only real if a commit that violates it is refused by the command an author
actually runs. So: a real repository, a real commit whose message carries the mistakes an
author actually makes — the wrong arrow, and a trailer someone invented — and the real
``atdd state trailers`` command, exiting non-zero and naming what to amend.

Then the canonical group, on a real commit, printing as the typed document the cross-check
consumes. Refs #1400.
"""
from __future__ import annotations

import pytest
import yaml

from ._helpers import TOKEN_DIGEST, UID_X
from ._live import atdd_state, commit, repo_on_bare_remote

PROJECTION_DIGEST = "sha256:" + "b2" * 32


@pytest.mark.smoke
def test_d001_smoke_001_commit_trailer_schema(tmp_path) -> None:
    """The real CLI refuses the unpinned trailer group and accepts the canonical one."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    # A real commit whose trailer block carries a wrong arrow and an invented trailer.
    commit(repo, "feat(x): move it along\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 "ATDD-Transition: PLANNED=>RED\n"   # wrong arrow
                 "ATDD-Whatever: x\n")               # not in the canonical group

    result = atdd_state(repo, "trailers", "--commit", "HEAD")

    assert result.returncode == 1, result.stdout + result.stderr
    out = result.stdout
    assert "ATDD-Transition" in out and "PLANNED=>RED" in out and "PHASE->PHASE" in out
    assert "ATDD-Whatever" in out and "unknown trailer" in out
    # The offending keys are named as such, so the author is told what to amend.
    assert "offending trailer: ATDD-Transition" in out
    assert "offending trailer: ATDD-Whatever" in out

    # The canonical section-5 group, on a real commit, parses and prints as a typed document.
    commit(repo, "feat(x): move it along\n\n"
                 f"ATDD-Object: {UID_X}\n"
                 "ATDD-Transition: PLANNED->RED\n"
                 f"ATDD-Token-Digest: {TOKEN_DIGEST}\n"
                 "ATDD-Gate: E019\n"
                 f"ATDD-Projection-Digest: {PROJECTION_DIGEST}\n")

    good = atdd_state(repo, "trailers", "--commit", "HEAD")
    assert good.returncode == 0, good.stdout + good.stderr

    document = yaml.safe_load(good.stdout)
    assert document["commit_kind"] == "single_object"
    assert document["ATDD-Object"] == UID_X
    assert document["ATDD-Transition"] == "PLANNED->RED"
    assert document["ATDD-Token-Digest"] == TOKEN_DIGEST
    assert document["ATDD-Gate"] == "E019"
    assert document["ATDD-Projection-Digest"] == PROJECTION_DIGEST

    # A uid that is not a `wi_` uid is refused on ATDD-Object — identity is the uid, and a
    # trailer that names an issue number instead is naming a mirror, not the object.
    commit(repo, "feat(x): move it along\n\nATDD-Object: 1400\n")
    bad_uid = atdd_state(repo, "trailers", "--commit", "HEAD")
    assert bad_uid.returncode == 1
    assert "ATDD-Object" in bad_uid.stdout
    assert "not a work-item uid" in bad_uid.stdout
