# URN: test:validate-conventions:shadow-and-promote:E016-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E016-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E016
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E016 — the shadow-run report must be honest: structural-only, behavioral parity
not established, legacy authoritative, decommission blocked. It must NOT be readable
as a behavioral-parity / zero-P0-gap claim while the #1206 engine is unbuilt."""
from __future__ import annotations

from pathlib import Path


def test_shadow_report_is_honest_about_parity(repo_root: Path) -> None:
    report = repo_root / "docs" / "validator-parity" / "shadow-run-report.md"
    assert report.exists(), f"shadow-run report not found at {report}"
    text = report.read_text(encoding="utf-8").lower()
    required = [
        "behavioral parity is not established",
        "legacy validators remain authoritative",
        "decommission is blocked",
    ]
    missing = [m for m in required if m not in text]
    assert not missing, (
        "shadow-run report is missing required honesty disclaimers "
        f"(could be misread as behavioral parity): {missing}"
    )
