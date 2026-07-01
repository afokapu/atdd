# URN: test:validate-conventions:legacy-parity-audit:E009-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E009-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E009
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E009 — every excluded file carries an explicit reason"""
from __future__ import annotations

from pathlib import Path

import yaml

def test_excluded_files_have_reason(repo_root: Path) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    assert map_path.exists(), f"parity map not found at {map_path}"
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    bad = [e.get("legacy_path") for e in (doc.get("excluded") or []) if not e.get("reason")]
    assert not bad, f"excluded files lacking a reason: {bad}"
