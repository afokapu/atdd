# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""``evidence_for`` path derivation — and the two directories that are NOT one thing.

``.atdd/evidence/`` and ``.atdd/smoke-evidence/`` read like a typo of each other and
are unrelated artifacts. The near-miss has already been mistaken for a bug once
(#1602's audit read the first as a dead branch with no producer), and the obvious
"fix" — pointing the merge-authority reader at the other — would create a false
green rather than close one. So the distinction is asserted here rather than left
to a comment:

``.atdd/evidence/<uid>/<gate>.yaml``
    The COMMITTED, per-gate merge-authority artifact. ``merge_driver`` owns the path
    and ``govern_cli._evidence_at`` reads it back with ``git ls-tree``/``git show``
    at the incoming commit. Its producer is a commit — by design, because evidence a
    merge cannot see is evidence the merge does not have (spec §6). Not gitignored.

``.atdd/smoke-evidence/<N>.yaml``
    The #358 presentation ratchet's LOCAL, gitignored, operator-TYPED stamp, written
    by ``atdd validate coder --smoke-required``, which runs no test. It can never
    reach the merge authority, and must never mint an evidence token if it somehow
    does.

``evidence_for`` had no test coverage at all before this file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.state.evidence import _MERGE_EVIDENCE_PREFIX, evidence_for
from atdd.state.merge_driver import EVIDENCE_RELATIVE

pytestmark = [pytest.mark.platform]

_REPO = Path(__file__).resolve().parents[4]

DOC = {"uid": "some-slug", "body": "a body", "wmbts": ["wmbt:x:E001"]}


def _tokens(*changed_paths: str) -> set:
    return evidence_for(DOC, list(changed_paths))


# --------------------------------------------------------------------------- #
# The two names, held apart                                                    #
# --------------------------------------------------------------------------- #


def test_the_prefix_matches_the_module_that_owns_the_path() -> None:
    """A rename of ``EVIDENCE_RELATIVE`` must not silently orphan the reader."""
    assert _MERGE_EVIDENCE_PREFIX == EVIDENCE_RELATIVE.as_posix() + "/", (
        "evidence_for reads a prefix that merge_driver no longer writes — the "
        "merge authority would stop seeing committed evidence and report green"
    )


def test_committed_merge_evidence_mints_the_smoke_token() -> None:
    """The live artifact: sharded per gate, and the flat form still read."""
    assert "smoke_evidence_artifact" in _tokens(".atdd/evidence/some-slug/GREEN->SMOKE.yaml")
    assert "smoke_evidence_artifact" in _tokens(".atdd/evidence/some-slug.yaml")


def test_the_operator_typed_stamp_never_mints_an_evidence_token() -> None:
    """`.atdd/smoke-evidence/` is a typed stamp, not evidence a merge may trust.

    If this ever starts passing a token, the merge authority has acquired a path
    to green that runs no test — the #1602 bug class, reintroduced one directory
    over.
    """
    tokens = _tokens(".atdd/smoke-evidence/1305.yaml")

    assert tokens == _tokens(), (
        "the presentation-ratchet stamp contributed an evidence token; it is "
        "producible by hand with `atdd validate coder --smoke-required`, which "
        "runs no test"
    )


def test_the_operator_typed_stamp_cannot_even_reach_a_commit() -> None:
    """Structural backstop: the stamp directory is gitignored.

    Belt and braces with the assertion above — that one says the reader would
    refuse it, this one says it can never be offered. Losing either is the moment
    the "just align the two directories" change becomes possible.
    """
    proc = subprocess.run(
        ["git", "check-ignore", "-q", ".atdd/smoke-evidence/1305.yaml"],
        cwd=str(_REPO), capture_output=True, timeout=30,
    )
    assert proc.returncode == 0, (
        ".atdd/smoke-evidence/ is no longer gitignored, so an operator-typed stamp "
        "can now land in a commit the merge authority reads"
    )


# --------------------------------------------------------------------------- #
# The rest of the v1 derivation, pinned                                        #
# --------------------------------------------------------------------------- #


def test_document_and_path_tokens_are_derived_as_documented() -> None:
    """The three sources, and only the three, each contributing what it can."""
    assert _tokens() == {"uid_generated", "body_initialized", "plan_complete",
                         "acceptance_or_wmbt_refs"}

    assert "implementation_diff" in _tokens("src/atdd/state/evidence.py")
    assert "implementation_diff" not in _tokens("docs/whatever.md")

    test_tokens = _tokens("src/atdd/state/tests/test_thing.py")
    assert {"failing_test_evidence", "passing_test_evidence"} <= test_tokens
    assert "smoke_evidence_artifact" not in test_tokens


def test_a_smoke_named_test_file_still_mints_the_v1_filename_token() -> None:
    """Pinned, not endorsed.

    Renaming any touched test file to contain ``smoke`` mints
    ``smoke_evidence_artifact``. The docstring on ``evidence_for`` concedes this is
    a deliberately mechanical v1 derivation; it is asserted here so that when it is
    tightened, the change is visible rather than incidental. It is also exactly why
    #1602's execution attestation lives in the store and NOT in this derivation —
    the merge authority can only read paths, and paths cannot tell you what ran.
    """
    assert "smoke_evidence_artifact" in _tokens("src/atdd/x/tests/test_smoke_thing.py")
