# URN: test:enforce-merge-authority:verify-trailer-diff:C002-UNIT-002-trailers-must-match-projection-diff
# Acceptance: acc:enforce-merge-authority:C002-UNIT-002-trailers-must-match-projection-diff
# WMBT: wmbt:enforce-merge-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: the cross-check admits the commit whose trailers and projection diff agree on object, transition and digest; rejects each of those three disagreements in turn naming the field and both sides; rejects a phase diff carrying no ATDD-Transition trailer; and admits a squash merge only when its ATDD-Summary artifact hashes to the digest the commit declared. Refs #1400.
"""Every trailer claim is bound to the diff it accompanies (C002-UNIT-002).

wagon: enforce-merge-authority | feature: verify-trailer-diff | phase: RED
WMBT: wmbt:enforce-merge-authority:C002

There are exactly three things a trailer group and a projection diff can disagree about —
the *object*, the *transition*, and the *digest* — and a fourth failure mode where the
diff moves a phase and the commit simply does not say so. Each is checked here, and each
rejection names the field and both sides.

The squash merge is the interesting one: it destroys the individual commits, so its event
semantics survive only in the ``ATDD-Summary`` artifact. An artifact whose digest does not
match is not a formatting nit — it is an event log that has been edited after the fact.
Refs #1400.
"""
from __future__ import annotations

import hashlib

from atdd.state import crosscheck
from atdd.state.trailers import parse_trailers

from ._helpers import (
    TOKEN_DIGEST,
    UID_X,
    UID_Y,
    digest_of,
    document,
    message,
    trailer_block,
)


def test_c002_unit_002_trailers_must_match_projection_diff(tmp_path) -> None:
    """The agreeing commit is admitted; each disagreement is rejected naming both sides."""
    base = {UID_X: document(UID_X, phase="PLANNED")}
    head = {UID_X: document(UID_X, phase="RED")}
    digest = digest_of(head[UID_X])

    def block(**kwargs):
        return parse_trailers(message("feat(x): to RED", trailer_block(UID_X, **kwargs)))

    agreeing = block(
        transition="PLANNED->RED", token_digest=TOKEN_DIGEST, gate="E019",
        projection_digest=digest,
    )

    # The agreeing commit is admitted.
    assert crosscheck.cross_check(agreeing, base, head).ok

    # Disagreement on the OBJECT: the commit claims an object whose projection did not move.
    wrong_object = parse_trailers(message(
        "feat(y): to RED", trailer_block(UID_Y, transition="PLANNED->RED", projection_digest=digest),
    ))
    report = crosscheck.cross_check(wrong_object, base, head)
    assert not report.ok
    objects = [d for d in report.disagreements if d.what == crosscheck.FIELD_OBJECT]
    # Both directions: the changed object is untrailered, AND the trailered object is unchanged.
    assert {(d.uid, d.trailer_side, d.projection_side) for d in objects} == {
        (UID_X, None, UID_X),
        (UID_Y, UID_Y, None),
    }

    # Disagreement on the TRANSITION: the trailer names a move the diff does not show.
    wrong_transition = block(transition="RED->GREEN", projection_digest=digest)
    report = crosscheck.cross_check(wrong_transition, base, head)
    assert not report.ok
    disagreement = next(d for d in report.disagreements if d.what == crosscheck.FIELD_TRANSITION)
    assert disagreement.trailer_side == "RED->GREEN"       # what the log claims
    assert disagreement.projection_side == "PLANNED->RED"  # what actually happened
    assert "RED->GREEN" in report.render() and "PLANNED->RED" in report.render()

    # Disagreement on the DIGEST.
    lie = "sha256:" + "ee" * 32
    report = crosscheck.cross_check(
        block(transition="PLANNED->RED", projection_digest=lie), base, head,
    )
    assert not report.ok
    disagreement = next(d for d in report.disagreements if d.what == crosscheck.FIELD_DIGEST)
    assert (disagreement.trailer_side, disagreement.projection_side) == (lie, digest)

    # A phase diff carrying NO ATDD-Transition trailer is rejected (spec §5 rule 2).
    report = crosscheck.cross_check(block(projection_digest=digest), base, head)
    assert not report.ok
    disagreement = next(d for d in report.disagreements if d.what == crosscheck.FIELD_TRANSITION)
    assert disagreement.trailer_side is None
    assert disagreement.projection_side == "PLANNED->RED"
    assert "no ATDD-Transition trailer" in report.render()

    # A squash merge is admitted when the summary artifact digest matches...
    artifact = tmp_path / ".atdd" / "events" / "9f2c1b7.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b'{"objects": ["wi_x"]}\n')
    true_digest = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
    squash = parse_trailers(message(
        "feat(x): squash-merge (#1400)",
        trailer_block(UID_X, transition="PLANNED->RED", projection_digest=digest),
        f"ATDD-Summary: .atdd/events/9f2c1b7.json\nATDD-Summary-Digest: {true_digest}",
    ))
    assert crosscheck.cross_check(squash, base, head, repo_root=tmp_path).ok

    # ...and rejected when it does not: an event log edited after the fact is not a log.
    tampered = parse_trailers(message(
        "feat(x): squash-merge (#1400)",
        trailer_block(UID_X, transition="PLANNED->RED", projection_digest=digest),
        f"ATDD-Summary: .atdd/events/9f2c1b7.json\nATDD-Summary-Digest: {'sha256:' + '00' * 32}",
    ))
    report = crosscheck.cross_check(tampered, base, head, repo_root=tmp_path)
    assert not report.ok
    disagreement = next(d for d in report.disagreements if d.what == crosscheck.FIELD_SUMMARY)
    assert disagreement.projection_side == true_digest
    assert "does not hash to its declared digest" in disagreement.detail
