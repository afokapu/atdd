# URN: test:implement-code:d005-anchor
# Acceptance: acc:implement-code:D005-UNIT-001-detect-ts-duplicates
# WMBT: wmbt:implement-code:D005
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


def test_d005_unit_001_detect_ts_duplicates() -> None:
    """Anchor stub for acc:implement-code:D005-UNIT-001-detect-ts-duplicates (real test pending)."""
    pytest.skip("substrate anchor stub — real wired test pending (#423)")
