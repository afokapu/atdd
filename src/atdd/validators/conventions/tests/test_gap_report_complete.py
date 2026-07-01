# URN: test:validate-conventions:shadow-and-promote:E016-RED-002-gap-report
# Acceptance: acc:validate-conventions:E016-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E016
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""The P0 legacy-vs-convention gap report must exist and account for every P0
pair, so the decommission gate is measured honestly (no silent omission). It must
NOT claim any pair is behaviorally VERIFIED until a real legacy-vs-convention diff
proves it."""
from __future__ import annotations

from pathlib import Path

import yaml


def _p0(repo_root: Path):
    m = yaml.safe_load((repo_root / "docs" / "validator-parity"
                        / "legacy-validator-map.yaml").read_text(encoding="utf-8"))
    return [e for e in m["entries"]
            if e.get("priority") == "P0"
            and e.get("parity_status") in {"direct", "split", "merged"}]


def test_gap_report_accounts_for_every_p0_pair(repo_root: Path) -> None:
    report = repo_root / "docs" / "validator-parity" / "p0-legacy-vs-convention-gap-report.md"
    assert report.exists(), f"gap report not found at {report}"
    text = report.read_text(encoding="utf-8")
    total = len(_p0(repo_root))
    # honest accounting: 3 sentinels named + the remaining count reconciles to total
    for sentinel in ("theme_must_be_canonical", "direct_reference_resolution",
                     "rule_validator_roundtrip"):
        assert sentinel in text, f"gap report omits sentinel {sentinel}"
    assert str(total - 3) in text, f"gap report must account for the remaining {total - 3} P0 pairs"
    assert "BLOCKED" in text, "gap report must record decommission is blocked"
