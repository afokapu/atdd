# URN: test:enforce-merge-authority:parse-commit-trailer:E001-UNIT-002-parses-grouped-and-summary-trailers
# Acceptance: acc:enforce-merge-authority:E001-UNIT-002-parses-grouped-and-summary-trailers
# WMBT: wmbt:enforce-merge-authority:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: parse_trailers returns a schema-valid typed trailer group for a single-object commit, one group per ATDD-Object for a grouped multi-object commit, and the summary trailers for a squash merge — and two parses of the same message return byte-identical results. Refs #1400.
"""The parser reads single, grouped and squash commits — deterministically (E001-UNIT-002).

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: RED
WMBT: wmbt:enforce-merge-authority:E001

Three commit shapes reach the protected branch and all three must become the same typed
structure (spec §5 rules 6–7): the ordinary single-object transition; the multi-object
commit that carries a *group* per object; and the squash merge, which loses the individual
commits and so must carry its event semantics in an ``ATDD-Summary`` artifact instead.

Determinism matters as much as coverage: CI parses the message, and so does the local
hook, and so will whoever audits the branch a year from now. If those three disagree, the
event log is not a log. Refs #1400.
"""
from __future__ import annotations

from atdd.state import trailers
from atdd.state.trailers import parse_trailers, validate_trailer_mapping

from ._helpers import TOKEN_DIGEST, UID_X, UID_Y

DIGEST_X = "sha256:" + "b2" * 32
DIGEST_Y = "sha256:" + "c3" * 32
SUMMARY_DIGEST = "sha256:" + "d4" * 32

SINGLE = f"""feat(x): move the object to RED

ATDD-Object: {UID_X}
ATDD-Transition: PLANNED->RED
ATDD-Token-Digest: {TOKEN_DIGEST}
ATDD-Gate: E019
ATDD-Projection-Digest: {DIGEST_X}
"""

GROUPED = f"""feat(x,y): move two objects at once

ATDD-Object: {UID_X}
ATDD-Transition: PLANNED->RED
ATDD-Token-Digest: {TOKEN_DIGEST}
ATDD-Gate: E019
ATDD-Projection-Digest: {DIGEST_X}

ATDD-Object: {UID_Y}
ATDD-Transition: RED->GREEN
ATDD-Projection-Digest: {DIGEST_Y}
"""

SQUASH = f"""feat(x): squash-merge the branch (#1400)

ATDD-Object: {UID_X}
ATDD-Transition: RED->GREEN
ATDD-Projection-Digest: {DIGEST_X}
ATDD-Summary: .atdd/events/9f2c1b7.json
ATDD-Summary-Digest: {SUMMARY_DIGEST}
"""


def test_e001_unit_002_parses_grouped_and_summary_trailers() -> None:
    """Each shape yields a schema-valid typed group, and two parses agree byte-for-byte."""
    single, grouped, squash = (parse_trailers(m) for m in (SINGLE, GROUPED, SQUASH))

    # Each call returns a schema-valid typed trailer group.
    for block in (single, grouped, squash):
        assert block.commit_kind in trailers.COMMIT_KINDS
        for group in block.groups:
            validate_trailer_mapping(group.as_mapping())

    # The single-object commit: one group, fully typed.
    assert single.commit_kind == trailers.SINGLE_OBJECT
    assert single.groups[0].object_uid == UID_X
    assert single.groups[0].phases == ("PLANNED", "RED")
    assert single.groups[0].token_digest == TOKEN_DIGEST
    assert single.groups[0].gate == "E019"

    # The grouped commit yields ONE trailer group per ATDD-Object, each with its own
    # digest — which is what lets the cross-check bind each object to its own diff.
    assert grouped.commit_kind == trailers.MULTI_OBJECT
    assert grouped.objects == (UID_X, UID_Y)
    assert grouped.group_for(UID_X).projection_digest == DIGEST_X
    assert grouped.group_for(UID_Y).projection_digest == DIGEST_Y
    assert grouped.group_for(UID_Y).transition == "RED->GREEN"
    assert grouped.group_for(UID_Y).token_digest is None  # trailers do not leak across groups

    # The squash commit yields the summary trailers and its summary digest.
    assert squash.commit_kind == trailers.SQUASH_MERGE
    assert squash.summary == ".atdd/events/9f2c1b7.json"
    assert squash.summary_digest == SUMMARY_DIGEST
    assert squash.group_for(UID_X).transition == "RED->GREEN"

    # Both calls on the same input return byte-identical results.
    for message, first in ((SINGLE, single), (GROUPED, grouped), (SQUASH, squash)):
        assert parse_trailers(message) == first
        assert parse_trailers(message).as_document() == first.as_document()

    # A commit with no ATDD trailers at all is not an error — it simply touches no
    # projection, and the cross-check has nothing to bind.
    assert parse_trailers("chore: tidy the README\n").commit_kind == trailers.NON_PROJECTION
