# URN: test:enforce-merge-authority:reject-history-secrets:C003-UNIT-001-raw-token-in-trailer-is-admitted
# Acceptance: acc:enforce-merge-authority:C003-UNIT-001-raw-token-in-trailer-is-admitted
# WMBT: wmbt:enforce-merge-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: an ATDD-Token-Digest trailer carrying a raw ghp_ token and a projection object whose external_refs embeds a bearer token are both reported as secrets, and the report redacts the matched value rather than echoing it into a CI log. Refs #1400.
"""A raw token in a trailer, and a credential in a projection, are refused (C003-UNIT-001).

wagon: enforce-merge-authority | feature: reject-history-secrets | phase: RED
WMBT: wmbt:enforce-merge-authority:C003

Git history is immutable (I8). Once a raw token is in a commit that reached the protected
branch it is there forever, and the only remaining response is to rotate the credential and
rewrite everyone's history. So the *only* place this can be caught is before the commit is
admitted.

Two surfaces carry the risk, and both are here: ``ATDD-Token-Digest`` is precisely the
trailer an author reaches for while holding an operator token, and ``external_refs`` carries
values a provider handed over. And the report **redacts** what it matched — a validator that
prints the secret it found has published it, into the CI log, on the way to telling you not
to. Refs #1400.
"""
from __future__ import annotations

from atdd.state import secrets

from ._helpers import UID_X, document

RAW_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0" + "K1L2M3"
BEARER = "Bearer eyJhbGciOiJIUzI1NiJ9.QUJDREVGR0hJSktMTU5PUFFS.c2lnbmF0dXJlLXZhbHVl"


def test_c003_unit_001_raw_token_in_trailer_is_admitted() -> None:
    """Both the trailer value and the projection value are reported — and neither is echoed."""
    trailers = {
        "ATDD-Object": UID_X,
        "ATDD-Token-Digest": RAW_TOKEN,   # a raw token where only a digest is admissible
    }
    projection = {
        UID_X: document(UID_X, external_refs={"github": {"authorization": BEARER}}),
    }

    report = secrets.scan(trailers=trailers, documents=projection)

    # Both are reported as secrets.
    assert not report.ok
    assert len(report.findings) == 2
    where = sorted(finding.where for finding in report.findings)
    assert where == [
        "trailer ATDD-Token-Digest",
        f"{UID_X}.external_refs.github.authorization",
    ]
    assert {finding.kind for finding in report.findings} == {"github_token", "bearer_token"}

    # The report REDACTS the matched value rather than echoing it. This is the whole
    # discipline: the finding must be enough to locate the value and useless to read.
    rendered = report.render()
    assert RAW_TOKEN not in rendered
    assert BEARER not in rendered
    assert "eyJhbGciOiJIUzI1NiJ9" not in rendered
    for finding in report.findings:
        assert "<redacted:" in finding.redacted
        assert RAW_TOKEN not in finding.redacted
        assert BEARER not in finding.redacted

    # The fingerprint still identifies the value: the same secret twice is recognisably one
    # secret, which is what makes a rotation actionable.
    assert secrets.redact(RAW_TOKEN, "github_token") == secrets.redact(RAW_TOKEN, "github_token")
    assert secrets.redact(RAW_TOKEN, "github_token") != secrets.redact(BEARER, "bearer_token")

    # The same commit with the token replaced by its digest is clean.
    assert secrets.scan(
        trailers={"ATDD-Object": UID_X, "ATDD-Token-Digest": "sha256:" + "a1" * 32},
        documents={UID_X: document(UID_X)},
    ).ok
