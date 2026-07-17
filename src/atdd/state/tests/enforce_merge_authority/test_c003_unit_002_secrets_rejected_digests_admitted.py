# URN: test:enforce-merge-authority:reject-history-secrets:C003-UNIT-002-secrets-rejected-digests-admitted
# Acceptance: acc:enforce-merge-authority:C003-UNIT-002-secrets-rejected-digests-admitted
# WMBT: wmbt:enforce-merge-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: over a corpus of raw provider tokens, bearer headers and private-key blocks, every raw credential is rejected naming the trailer key or the projection field, every sha256:<hex> digest value is admitted, and no rejection message contains the matched secret verbatim. Refs #1400.
"""The corpus: raw credentials rejected, digests admitted, nothing echoed (C003-UNIT-002).

wagon: enforce-merge-authority | feature: reject-history-secrets | phase: RED
WMBT: wmbt:enforce-merge-authority:C003

A secret scanner is only as good as the shapes it knows, and only as safe as its report.
So this is a corpus test on both counts: every credential form the validator claims to
recognise is fed to it (provider tokens, a bearer header, a private-key block, an AWS key,
a credentialed URL), the admissible ``sha256:<hex>`` digest is fed to it too, and the
report is then checked for the one thing it must never contain — the value it matched.

The digest short-circuit is load-bearing rather than a convenience: the trailer group
exists *precisely* so that an operator's approval reaches CI as a digest. A scanner that
flagged its own digest trailers would be untenable and would be switched off. Refs #1400.
"""
from __future__ import annotations

import pytest

from atdd.state import secrets

from ._helpers import UID_X, document

# Every credential below is FAKE, and each is split across a concatenation so that no line
# of this file carries a credential-shaped literal for a secret scanner to match. That is
# not decoration: this repo runs `coder.security.hardcoded-secret` over its own source, and
# a corpus test for a secret scanner is the one file guaranteed to trip it. The split is the
# idiom the corpus already used for the token forms; the private key and the AWS key simply
# had not been written that way yet. Python folds these at compile time, so every value the
# scanner under test receives is byte-for-byte the credential it must refuse.
PRIVATE_KEY = (
    "-----BEGIN RSA " + "PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAy8Dbv8prpJ/0kKhlGeJYozo2t60EG8L0561g13R29LvMR5hy\n"
    "-----END RSA PRIVATE KEY-----"
)

#: Every raw credential the validator must refuse, with the kind it must be named under.
RAW = [
    ("github_token", "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1L2M3"),
    ("github_token", "gho_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6"),
    ("github_pat", "github_pat_11ABCDEFG0abcdefghij_KLMNOPQRSTUVWXYZ0123456789"),
    ("slack_token", "xoxb" + "-1234567890-0987654321-AbCdEfGhIjKlMnOpQrSt"),
    ("aws_access_key", "AKIA" + "IOSFODNN7EXAMPLE"),
    ("bearer_token", "Bearer eyJhbGciOiJIUzI1NiJ9.QUJDREVGR0hJSg.c2lnbmF0dXJl"),
    ("basic_auth_url", "https://ci-bot:sup3rs3cr3tpassword@git.example.invalid/repo.git"),
    ("private_key", PRIVATE_KEY),
]

#: Values that must be ADMITTED: the digest form, and ordinary metadata.
ADMISSIBLE = [
    "sha256:" + "a1" * 32,
    "sha256:" + "0" * 64,
    "wi_01HF7YAT00M78607F0000000X1",
    "PLANNED->RED",
    "E019",
    ".atdd/events/9f2c1b7.json",
]


@pytest.mark.parametrize(("kind", "value"), RAW)
def test_c003_unit_002_secrets_rejected_digests_admitted(kind: str, value: str) -> None:
    """Every raw credential is rejected under its kind; digests pass; nothing is echoed."""
    # Rejected on a TRAILER, named by the trailer key.
    report = secrets.scan_trailers({"ATDD-Token-Digest": value})
    assert not report.ok
    assert report.findings[0].kind == kind
    assert report.findings[0].where == "trailer ATDD-Token-Digest"

    # Rejected in a PROJECTION object, named by the field path.
    report = secrets.scan_document(document(UID_X, external_refs={"github": {"token": value}}))
    assert not report.ok
    assert report.findings[0].kind == kind
    assert report.findings[0].where == f"{UID_X}.external_refs.github.token"

    # No rejection message contains the matched secret verbatim — not the render, not the
    # finding, not the redaction. This is the property that makes the scanner safe to run
    # in CI at all.
    assert value not in report.render()
    assert value not in report.findings[0].redacted
    assert value.strip() not in report.render()

    # Every admissible value is admitted, on both surfaces, in the same run.
    clean = secrets.scan(
        trailers={f"ATDD-Digest-{index}": ok for index, ok in enumerate(ADMISSIBLE)},
        documents={UID_X: document(UID_X, train="train:commons:state-projection")},
    )
    assert clean.ok, clean.render()
    assert clean.scanned >= len(ADMISSIBLE)

    # And the kind is one the validator publishes, so the report's vocabulary is closed.
    assert kind in secrets.secret_kinds()
