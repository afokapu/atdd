# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E004-SMOKE-001-validator-over-live-surface-names
# Acceptance: acc:consolidate-coach-workspace:E004-SMOKE-001-validator-over-live-surface-names
# WMBT: wmbt:consolidate-coach-workspace:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004-SMOKE-001 — run the bound role-aware naming validator over a REAL cmux
``surface.list``. A coach-managed surface named in the role-aware scheme passes;
a name lacking the role segment is flagged for re-application. Runs wherever cmux
is on PATH; skips otherwise."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_e004_smoke_001_validator_over_live_surface_names(tmp_path):
    from atdd.consolidate_coach_workspace.enforce_surface_conformance.live_smoke import (
        naming_validator_live_smoke,
    )

    evidence = naming_validator_live_smoke(
        evidence_path=str(tmp_path / "evidence.txt")
    )

    # a role-aware managed surface name passed the validator
    assert evidence["conforming_name"]
    assert evidence["conforming_passed"] is True
    # a drifted (no-role) name was flagged
    assert evidence["drifted_name"]
    assert evidence["drifted_flagged"] is True
