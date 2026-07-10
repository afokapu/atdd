# URN: test:enforce-merge-authority:reject-history-secrets:C003-UNIT-002-secrets-rejected-digests-admitted
# Acceptance: acc:enforce-merge-authority:C003-UNIT-002-secrets-rejected-digests-admitted
# WMBT: wmbt:enforce-merge-authority:C003
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:enforce-merge-authority:C003-UNIT-002-secrets-rejected-digests-admitted — fails until the enforce-merge-authority wagon implements it. Refs #1400.
"""RED skeleton for acc:enforce-merge-authority:C003-UNIT-002-secrets-rejected-digests-admitted.

wagon: enforce-merge-authority | feature: reject-history-secrets | phase: RED
WMBT: wmbt:enforce-merge-authority:C003

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the enforce-merge-authority wagon lands the behaviour (raw secrets are rejected while digest-only trailer values are admitted (invariant I8)). When it
xpasses, drop the xfail marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest

@pytest.mark.xfail(strict=True, reason="enforce-merge-authority not yet implemented (RED; #1400)")
def test_c003_unit_002_secrets_rejected_digests_admitted() -> None:
    """C003-UNIT-002-secrets-rejected-digests-admitted — behaviour not yet implemented."""
    raise AssertionError(
        "RED: enforce-merge-authority acceptance acc:enforce-merge-authority:C003-UNIT-002-secrets-rejected-digests-admitted is not implemented yet"
    )
