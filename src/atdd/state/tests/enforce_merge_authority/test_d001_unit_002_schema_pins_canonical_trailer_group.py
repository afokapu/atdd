# URN: test:enforce-merge-authority:parse-commit-trailer:D001-UNIT-002-schema-pins-canonical-trailer-group
# Acceptance: acc:enforce-merge-authority:D001-UNIT-002-schema-pins-canonical-trailer-group
# WMBT: wmbt:enforce-merge-authority:D001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the schema accepts the canonical section-5 trailer group and pins each value grammar — a non-wi_ uid, an off-vocabulary phase and a non-sha256 digest are each rejected on the trailer that carries them — and it declares ATDD-Summary/ATDD-Summary-Digest for squash merges; the executable schema is tied to the authored commons:projection-trailer contract. Refs #1400.
"""The trailer schema pins the canonical group and every value grammar (D001-UNIT-002).

wagon: enforce-merge-authority | feature: parse-commit-trailer | phase: RED
WMBT: wmbt:enforce-merge-authority:D001

Section 5's group is the whole contract between a commit and the state it claims to
change: ``ATDD-Object`` (a uid), ``ATDD-Transition`` (PHASE->PHASE), ``ATDD-Token-Digest``
and ``ATDD-Projection-Digest`` (``sha256:<hex>``, never the secret itself), ``ATDD-Gate``
(a gate id), plus ``ATDD-Summary``/``ATDD-Summary-Digest`` for a squash merge.

The authored ``commons:projection-trailer`` contract is the source of truth for that
shape; the module's constants are its executable form. This test ties the two together,
so a change to one that is not a change to the other fails here rather than in CI. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import trailers
from atdd.state.trailers import (
    DIGEST_RE,
    TRAILER_KEYS,
    TRANSITION_RE,
    TrailerSchemaError,
    validate_trailer_mapping,
)

from ._helpers import TOKEN_DIGEST, UID_X, contract

PROJECTION_DIGEST = "sha256:" + "b2" * 32


def test_d001_unit_002_schema_pins_canonical_trailer_group() -> None:
    """The canonical group validates clean; every value grammar is pinned and enforced."""
    canonical = {
        "ATDD-Object": UID_X,
        "ATDD-Transition": "PLANNED->RED",
        "ATDD-Token-Digest": TOKEN_DIGEST,
        "ATDD-Gate": "E019",
        "ATDD-Projection-Digest": PROJECTION_DIGEST,
    }
    validate_trailer_mapping(canonical)  # the canonical group validates clean

    # A uid that is not a `wi_` uid is rejected ON ATDD-Object.
    with pytest.raises(TrailerSchemaError, match=r"ATDD-Object"):
        validate_trailer_mapping({**canonical, "ATDD-Object": "1400"})

    # A transition whose phases are outside the phase-machine vocabulary is rejected.
    with pytest.raises(TrailerSchemaError, match=r"outside the phase-machine vocabulary"):
        validate_trailer_mapping({**canonical, "ATDD-Transition": "PLANNED->SHIPPED"})

    # A digest that is not sha256:<hex> is rejected on EVERY digest trailer.
    for key in ("ATDD-Token-Digest", "ATDD-Projection-Digest", "ATDD-Summary-Digest"):
        with pytest.raises(TrailerSchemaError) as caught:
            validate_trailer_mapping({**canonical, key: "md5:deadbeef"})
        assert key in str(caught.value)
        # The refusal does NOT echo the value: an ungrammatical digest trailer is exactly
        # where a raw token turns up, and a validator that prints it has leaked it (I8).
        assert "md5:deadbeef" not in str(caught.value)

    # The schema declares ATDD-Summary and ATDD-Summary-Digest for squash merges.
    assert "ATDD-Summary" in TRAILER_KEYS
    assert "ATDD-Summary-Digest" in TRAILER_KEYS
    validate_trailer_mapping({
        "ATDD-Summary": ".atdd/events/abc123.json",
        "ATDD-Summary-Digest": PROJECTION_DIGEST,
    })
    with pytest.raises(TrailerSchemaError, match=r"ATDD-Summary"):
        validate_trailer_mapping({"ATDD-Summary": "notes.txt"})

    # The executable schema IS the authored contract, not a lookalike of it.
    authored = contract("projection-trailer")
    properties = authored["properties"]
    assert set(TRAILER_KEYS) == {key for key in properties if key.startswith("ATDD-")}
    assert properties["ATDD-Transition"]["pattern"] == TRANSITION_RE.pattern
    for key in ("ATDD-Token-Digest", "ATDD-Projection-Digest", "ATDD-Summary-Digest"):
        assert properties[key]["pattern"] == DIGEST_RE.pattern
    assert set(properties["commit_kind"]["enum"]) == set(trailers.COMMIT_KINDS)
    # A grouped multi-object commit must carry a complete group per object.
    assert properties["groups"]["items"]["required"] == ["ATDD-Object", "ATDD-Projection-Digest"]

    # And the schema pins the *cardinality* rules too: which trailers a diff class requires.
    # Rule 1 + 4: any projection object diff carries the object and its digest.
    assert trailers.required_trailers("projection_object") == (
        "ATDD-Object", "ATDD-Projection-Digest",
    )
    # Rule 2: a phase diff additionally carries the transition.
    assert "ATDD-Transition" in trailers.required_trailers("phase")
    # Rule 3: a gated transition additionally carries the token digest and the gate id.
    gated = trailers.required_trailers("gated_transition")
    assert "ATDD-Token-Digest" in gated and "ATDD-Gate" in gated
    # Rules 6-7: a squash merge carries the summary artifact and its digest.
    assert trailers.required_trailers("squash_merge") == ("ATDD-Summary", "ATDD-Summary-Digest")

    with pytest.raises(KeyError):
        trailers.required_trailers("something-else")
