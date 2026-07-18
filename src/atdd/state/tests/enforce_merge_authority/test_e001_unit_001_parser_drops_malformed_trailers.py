# URN: test:enforce-merge-authority:parse-commit-trailer:E001-UNIT-001-parser-drops-malformed-trailers
# Acceptance: acc:enforce-merge-authority:E001-UNIT-001-parser-drops-malformed-trailers
# WMBT: wmbt:enforce-merge-authority:E001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: parse_trailers refuses a malformed trailer block instead of silently dropping it — a duplicate ATDD-Object and a non-sha256 ATDD-Token-Digest each raise TrailerParseError naming the offending trailer key, and no partially-parsed group is ever returned. Refs #1400.
"""A malformed trailer block is refused, never half-parsed (E001-UNIT-001).

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: RED
WMBT: wmbt:enforce-merge-authority:E001

Silently dropping a malformed trailer is the worst available option: the cross-check that
runs next would then compare the projection diff against *half* a trailer group and report
agreement it never actually verified. So the parser refuses, and it names the offending
trailer key — a duplicate ``ATDD-Object`` (two contradictory claims about one object in
one commit) and an ``ATDD-Token-Digest`` that is not ``sha256:<hex>``. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.trailers import TrailerParseError, parse_trailers

from ._helpers import UID_X

MALFORMED = f"""feat(thing): do the thing

ATDD-Object: {UID_X}
ATDD-Transition: PLANNED->RED
ATDD-Object: {UID_X}
ATDD-Token-Digest: ghp_thisisnotadigestitisatoken000000000
ATDD-Projection-Digest: sha256:{'c3' * 32}
"""


def test_e001_unit_001_parser_drops_malformed_trailers() -> None:
    """The parser raises, names both offending keys, and returns nothing at all."""
    with pytest.raises(TrailerParseError) as caught:
        parse_trailers(MALFORMED)

    error = caught.value

    # The offending trailer keys are named — the author is told what to amend.
    assert "ATDD-Object" in error.keys
    assert "ATDD-Token-Digest" in error.keys
    assert "duplicate ATDD-Object" in str(error)
    assert "ATDD-Token-Digest is not a sha256:<hex> digest" in str(error)

    # The refusal does not echo the raw token it refused (I8): it was a credential a
    # moment ago, and printing it into a CI log publishes it.
    assert "ghp_thisisnotadigestitisatoken000000000" not in str(error)

    # The malformed block is never returned as a partially-parsed trailer group: the call
    # raised, so there is no half-group for the cross-check to trust.
    assert isinstance(error, TrailerParseError)
    assert error.problems  # every problem, not merely the first

    # The same message with the faults fixed parses — the refusal was about the block, not
    # about the parser being unable to read a commit at all.
    fixed = MALFORMED.replace(
        f"ATDD-Object: {UID_X}\nATDD-Token-Digest: ghp_thisisnotadigestitisatoken000000000",
        f"ATDD-Token-Digest: sha256:{'a1' * 32}",
    )
    block = parse_trailers(fixed)
    assert block.objects == (UID_X,)
