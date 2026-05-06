# URN: test:govern-lifecycle:d015-anchor
# Acceptance: acc:govern-lifecycle:D015-UNIT-001-cmux-backend-surface-dispatch
# Acceptance: acc:govern-lifecycle:D015-UNIT-002-new-surface-creates-pane-then-surface
# WMBT: wmbt:govern-lifecycle:D015
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


def test_d015_unit_001_cmux_backend_surface_dispatch() -> None:
    """Anchor stub for acc:govern-lifecycle:D015-UNIT-001-cmux-backend-surface-dispatch (real test pending)."""
    pytest.skip("substrate anchor stub — real wired test pending (#423)")

def test_d015_unit_002_new_surface_creates_pane_then_surface() -> None:
    """Anchor stub for acc:govern-lifecycle:D015-UNIT-002-new-surface-creates-pane-then-surface (real test pending)."""
    pytest.skip("substrate anchor stub — real wired test pending (#423)")
