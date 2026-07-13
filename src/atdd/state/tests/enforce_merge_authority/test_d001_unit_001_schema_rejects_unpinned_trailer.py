# URN: test:enforce-merge-authority:parse-commit-trailer:D001-UNIT-001-schema-rejects-unpinned-trailer
# Acceptance: acc:enforce-merge-authority:D001-UNIT-001-schema-rejects-unpinned-trailer
# WMBT: wmbt:enforce-merge-authority:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the trailer schema refuses an ungrammatical ATDD-Transition value and an unknown ATDD-* trailer key, naming both in one refusal; the canonical group is closed, so an unpinned trailer is a violation and not a harmless extra. Refs #1400.
"""An unpinned or ungrammatical ATDD trailer is refused (D001-UNIT-001).

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: RED
WMBT: wmbt:enforce-merge-authority:D001

Git history is only an event log if the trailer group is *pinned*: closed, with a value
grammar per trailer. Without that, ``ATDD-Transition: PLANNED=>RED`` reads as "no
transition declared" to a parser and as "a transition declared" to the human who wrote
it — and an unknown ``ATDD-Whatever`` invites the group to grow a dialect per author.
Both are refused, and the refusal names what to fix. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.trailers import TrailerSchemaError, validate_trailer_mapping


def test_d001_unit_001_schema_rejects_unpinned_trailer() -> None:
    """The wrong-arrow transition and the unknown trailer are both named in the refusal."""
    block = {
        "ATDD-Object": "wi_01HF7YAT00M78607F0000000X1",
        "ATDD-Transition": "PLANNED=>RED",   # wrong arrow: the grammar is PHASE->PHASE
        "ATDD-Whatever": "x",                # not in the canonical group
    }

    with pytest.raises(TrailerSchemaError) as caught:
        validate_trailer_mapping(block)

    problem = str(caught.value)

    # The ungrammatical value is named, and so is the trailer that carries it.
    assert "ATDD-Transition" in problem
    assert "PLANNED=>RED" in problem
    assert "PHASE->PHASE" in problem

    # The unknown trailer key is named too — the group is closed, not merely conventional.
    assert "ATDD-Whatever" in problem
    assert "unknown trailer" in problem

    # Both faults come out of ONE call: an author fixing a commit message wants every
    # problem at once, not one per amend.
    assert problem.count(";") >= 1

    # The well-formed group the block was *trying* to be validates clean.
    validate_trailer_mapping({
        "ATDD-Object": "wi_01HF7YAT00M78607F0000000X1",
        "ATDD-Transition": "PLANNED->RED",
    })
