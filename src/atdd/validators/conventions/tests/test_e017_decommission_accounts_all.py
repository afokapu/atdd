# URN: test:validate-conventions:legacy-decommission:E017-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E017-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E017
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E017 — the decommission report records an outcome for every legacy validator"""
from __future__ import annotations

from pathlib import Path

import yaml

LEGACY_ROOTS = ["src/atdd/planner/validators","src/atdd/tester/validators","src/atdd/coder/validators","src/atdd/coach/validators"]

def test_decommission_report_accounts_for_all_legacy(repo_root: Path) -> None:
    report = repo_root / "docs" / "validator-parity" / "legacy-validator-decommission-report.md"
    assert report.exists(), f"decommission report not found at {report}"
    text = report.read_text(encoding="utf-8")
    missing = []
    for root in LEGACY_ROOTS:
        for f in (repo_root / root).glob("test_*.py"):
            if f"{root}/{f.name}" not in text and f.name not in text:
                missing.append(f"{root}/{f.name}")
    assert not missing, f"legacy validators with no decommission outcome: {missing}"
