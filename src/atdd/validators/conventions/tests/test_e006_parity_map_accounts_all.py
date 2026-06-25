# URN: test:validate-conventions:legacy-parity-audit:E006-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E006-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E006
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E006 — every file under the four legacy roots is accounted for in the parity map"""
from __future__ import annotations

from pathlib import Path

import yaml

LEGACY_ROOTS = ["src/atdd/planner/validators","src/atdd/tester/validators","src/atdd/coder/validators","src/atdd/coach/validators"]

def test_every_legacy_validator_is_accounted_for(repo_root: Path) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    assert map_path.exists(), f"parity map not found at {map_path}"
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    accounted = {e.get("legacy_path") for e in (doc.get("entries") or [])}
    accounted |= {e.get("legacy_path") for e in (doc.get("excluded") or [])}
    actual = set()
    for root in LEGACY_ROOTS:
        for f in (repo_root / root).glob("*.py"):
            actual.add(f"{root}/{f.name}")
    unaccounted = sorted(actual - accounted)
    assert not unaccounted, f"legacy validators not in parity map: {unaccounted}"
