# URN: test:validate-conventions:p0-graph-integrity-variants:E010-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E010-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E010
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E010 — every P0 buildable parity entry has a target variant implementation"""
from __future__ import annotations

from pathlib import Path

import yaml

BUILDABLE = {"direct","split","merged","superseded"}

def test_p0_buildable_entries_have_target(repo_root: Path) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    assert map_path.exists(), f"parity map not found at {map_path}"
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    missing = []
    for e in (doc.get("entries") or []):
        if e.get("priority") == "P0" and e.get("parity_status") in BUILDABLE:
            tgt = e.get("proposed_target_path")
            if e.get("parity_status") == "superseded":
                continue
            if not tgt or not (repo_root / tgt).exists():
                missing.append(f"{e.get('legacy_path')} -> {tgt}")
    assert not missing, f"P0 entries without a target implementation: {missing}"
