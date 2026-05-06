# URN: test:self-compliance-migration:e002-anchor
# Acceptance: acc:self-compliance-migration:E002-UNIT-001-contracts-pass-schema
# WMBT: wmbt:self-compliance-migration:E002
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: Substrate Class 1 anchor stub (#423). Real wired tests pending; see docs/substrate-worked-example.md.

"""Anchor stub for substrate Class 1 bidirectional binding (issue #423).

Each test below is a pytest.skip placeholder. The header above declares
`# Acceptance: <urn>` for every acceptance under this WMBT, satisfying the
bidirectional-binding rule until real wired tests are written elsewhere
in the toolkit.

Delete a function when its acceptance gets a real wired test (anchor it
from the real test file). Delete this file when every acceptance under
the WMBT is covered.
"""

from __future__ import annotations

import pytest


def test_e002_unit_001_contracts_pass_schema() -> None:
    """Anchor stub for acc:self-compliance-migration:E002-UNIT-001-contracts-pass-schema (real test pending)."""
    pytest.skip("substrate anchor stub — real wired test pending (#423)")
