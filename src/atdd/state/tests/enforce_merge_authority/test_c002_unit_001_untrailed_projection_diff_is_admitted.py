# URN: test:enforce-merge-authority:verify-trailer-diff:C002-UNIT-001-untrailed-projection-diff-is-admitted
# Acceptance: acc:enforce-merge-authority:C002-UNIT-001-untrailed-projection-diff-is-admitted
# WMBT: wmbt:enforce-merge-authority:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a commit that changes a projection object while carrying no ATDD-Object trailer is reported as a missing trailer, and a commit whose ATDD-Projection-Digest disagrees with the projection it commits is reported naming BOTH digests — the git event log may not drift from the state it claims to describe. Refs #1400.
"""An untrailed projection diff, and a lying digest, are both reported (C002-UNIT-001).

wagon: enforce-merge-authority | feature: verify-trailer-diff | phase: RED
WMBT: wmbt:enforce-merge-authority:C002

When the trailers and the projection diff disagree, the git event log has quietly stopped
describing shared state — and a wrong audit log is worse than no audit log, because it is
*believed*. Two ways it goes wrong, and both are silent without this cross-check: a
projection object changes with no ``ATDD-Object`` trailer at all (the change happened and
the log says nothing), and an ``ATDD-Projection-Digest`` disagrees with the bytes the
commit actually committed (the log says something, and it is false). Refs #1400.
"""
from __future__ import annotations

from atdd.state import crosscheck
from atdd.state.trailers import parse_trailers

from ._helpers import UID_X, digest_of, document, message, trailer_block


def test_c002_unit_001_untrailed_projection_diff_is_admitted() -> None:
    """The missing ATDD-Object trailer is named, and the digest disagreement names both sides."""
    base = {UID_X: document(UID_X, phase="PLANNED")}
    head = {UID_X: document(UID_X, phase="PLANNED", body="a body the commit added")}

    # 1. A commit that changes .atdd/state/projection/wi_x.yaml and carries NO ATDD-Object.
    untrailed = parse_trailers("chore: tidy things up\n")
    report = crosscheck.cross_check(untrailed, base, head)

    assert not report.ok
    assert report.checked == 1
    missing = [d for d in report.disagreements if d.what == crosscheck.FIELD_OBJECT]
    assert len(missing) == 1
    assert missing[0].uid == UID_X
    assert missing[0].trailer_side is None          # the trailers say nothing...
    assert missing[0].projection_side == UID_X      # ...and the projection says otherwise
    assert "no ATDD-Object trailer" in report.render()

    # 2. A commit whose ATDD-Projection-Digest disagrees with the projection it commits.
    wrong_digest = "sha256:" + "ff" * 32
    lying = parse_trailers(message(
        "feat(x): update the body",
        trailer_block(UID_X, projection_digest=wrong_digest),
    ))
    report = crosscheck.cross_check(lying, base, head)

    assert not report.ok
    disagreement = next(d for d in report.disagreements if d.what == crosscheck.FIELD_DIGEST)

    # The disagreement is reported naming BOTH digests — "mismatch" is an accusation,
    # "trailer says X, projection says Y" is a diagnosis.
    assert disagreement.trailer_side == wrong_digest
    assert disagreement.projection_side == digest_of(head[UID_X])
    assert disagreement.trailer_side != disagreement.projection_side
    rendered = report.render()
    assert wrong_digest in rendered
    assert digest_of(head[UID_X]) in rendered

    # The truthful commit — same diff, honest trailers — is admitted.
    honest = parse_trailers(message(
        "feat(x): update the body",
        trailer_block(UID_X, projection_digest=digest_of(head[UID_X])),
    ))
    assert crosscheck.cross_check(honest, base, head).ok
