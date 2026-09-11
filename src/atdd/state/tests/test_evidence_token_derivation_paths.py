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

from atdd.state.evidence import EVIDENCE_POLICY, PHASE_LADDER, evidence_for
from atdd.state.evidence_paths import MERGE_EVIDENCE_PREFIX
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
    assert MERGE_EVIDENCE_PREFIX == EVIDENCE_RELATIVE.as_posix() + "/", (
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


# --------------------------------------------------------------------------- #
# The prefix is a directory, not a licence (#1945)                             #
# --------------------------------------------------------------------------- #


def test_an_unrelated_file_under_the_prefix_mints_nothing() -> None:
    """A README in the evidence directory is not smoke evidence.

    ``smoke_evidence_artifact`` is the sole requirement of BOTH ``GREEN->SMOKE``
    and ``SMOKE->REFACTOR``, so a branch that mints it from a bare directory
    prefix hands any committed file in that directory a walk out of SMOKE. That
    is the #1602 bug class arriving from the other direction: not a typed stamp
    read as evidence, but an arbitrary path read as one.
    """
    for path in (
        ".atdd/evidence/README.md",
        ".atdd/evidence/notes.txt",
        ".atdd/evidence/some-slug/anything.txt",
        ".atdd/evidence/some-slug/probe-can-framework-x.yaml",
    ):
        assert _tokens(path) == _tokens(), (
            f"{path} minted an evidence token; it names no gate, so it attests "
            "to no transition"
        )


def test_another_objects_evidence_does_not_evidence_this_one() -> None:
    """Evidence is per-object, and the reader that owns the path says so.

    ``govern_cli._evidence_at`` scopes its ``git ls-tree`` to
    ``.atdd/evidence/<uid>/``. The derivation is handed every path in the commit
    for every object in it, so an unscoped prefix test lets one object's
    honestly-earned artifact evidence every other object advancing in the same
    commit.
    """
    assert _tokens(".atdd/evidence/other-slug/GREEN->SMOKE.yaml") == _tokens(), (
        "another object's gate artifact minted this object's smoke evidence"
    )
    assert _tokens(".atdd/evidence/other-slug.yaml") == _tokens()


def test_the_documented_gate_artifact_shapes_still_mint() -> None:
    """The narrowing must not close the path the merge authority actually uses.

    Both separator spellings are live in-tree — ``write_evidence`` is called with
    ``PLANNED-RED`` by the live projection-merge tests, and ``GREEN->SMOKE`` by
    this file — so both are read.
    """
    for path in (
        ".atdd/evidence/some-slug/GREEN->SMOKE.yaml",
        ".atdd/evidence/some-slug/GREEN-SMOKE.yaml",
        ".atdd/evidence/some-slug/PLANNED-RED.yaml",
        ".atdd/evidence/some-slug/RED-GREEN.yaml",
        ".atdd/evidence/some-slug/INIT.yaml",
        ".atdd/evidence/some-slug.yaml",
    ):
        assert "smoke_evidence_artifact" in _tokens(path), (
            f"{path} is the committed per-gate artifact and stopped minting — the "
            "merge authority has gone blind to real evidence"
        )


def _policy_gate_names() -> list:
    """Every filename stem that names a gate in :data:`EVIDENCE_POLICY`.

    An entry with no ``from`` is the ``* -> TOMBSTONED`` wildcard, so it names one
    gate per rung; an entry with ``from: None`` is the mint, whose only source is
    the empty set and whose name is therefore the target phase alone.
    """
    names: list = []
    for entry in EVIDENCE_POLICY["transitions"]:
        to_phase = entry["to"]
        if "from" not in entry:
            sources = list(PHASE_LADDER)
        elif entry["from"] is None:
            names.append(to_phase)
            continue
        else:
            sources = [entry["from"]]
        for source in sources:
            names.extend((f"{source}->{to_phase}", f"{source}-{to_phase}"))
    return names


@pytest.mark.parametrize("gate_name", _policy_gate_names())
def test_every_policy_gate_has_an_artifact_name_that_mints(gate_name) -> None:
    """A gate added to the §6 table becomes an admissible artifact name by that edit.

    Asserted through the derivation rather than against a private set, because a
    hand-maintained second list of gate names would drift from
    :data:`EVIDENCE_POLICY`, and the drift would read to an operator as "the
    evidence is missing" rather than as "the filename is unrecognised".
    """
    path = f"{MERGE_EVIDENCE_PREFIX}{DOC['uid']}/{gate_name}.yaml"

    assert "smoke_evidence_artifact" in _tokens(path), (
        f"{gate_name} names a transition in EVIDENCE_POLICY, but an artifact "
        "filed under that name attests to nothing"
    )
