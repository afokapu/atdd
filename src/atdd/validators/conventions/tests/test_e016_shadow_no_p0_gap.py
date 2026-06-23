# URN: test:validate-conventions:shadow-and-promote:E016-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E016-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E016
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E016 — the shadow-run report shows zero unresolved P0 parity gaps"""
from __future__ import annotations

from pathlib import Path

import yaml

def test_shadow_report_has_no_unresolved_p0_gaps(repo_root: Path) -> None:
    report = repo_root / "docs" / "validator-parity" / "shadow-run-report.md"
    assert report.exists(), f"shadow-run report not found at {report}"
    text = report.read_text(encoding="utf-8").lower()
    assert "unresolved p0" not in text or "unresolved p0: 0" in text, (
        "shadow-run report still lists unresolved P0 parity gaps"
    )
