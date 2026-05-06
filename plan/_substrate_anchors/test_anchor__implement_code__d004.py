# URN: test:implement-code:d004-anchor
# Acceptance: acc:implement-code:D004-UNIT-001-detect-duplicates
# Acceptance: acc:implement-code:D004-UNIT-002-convention-compliance
# WMBT: wmbt:implement-code:D004
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


def test_d004_unit_001_detect_duplicates() -> None:
    """Anchor stub for acc:implement-code:D004-UNIT-001-detect-duplicates (real test pending)."""
    pytest.skip("substrate anchor stub — real wired test pending (#423)")

def test_d004_unit_002_convention_compliance() -> None:
    """Anchor stub for acc:implement-code:D004-UNIT-002-convention-compliance (real test pending)."""
    pytest.skip("substrate anchor stub — real wired test pending (#423)")
