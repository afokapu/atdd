# URN: test:validate-conventions:p1-parity-variants:E012-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E012-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E012
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E012 — every P1 buildable parity entry is implemented or deferred with a reason"""
from __future__ import annotations

from pathlib import Path

import yaml

BUILDABLE = {"direct","split","merged","superseded"}

def test_p1_entries_built_or_deferred(repo_root: Path) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    assert map_path.exists(), f"parity map not found at {map_path}"
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    unresolved = []
    for e in (doc.get("entries") or []):
        if e.get("priority") == "P1" and e.get("parity_status") in BUILDABLE:
            tgt = e.get("proposed_target_path")
            built = bool(tgt) and (repo_root / tgt).exists()
            deferred = bool(e.get("deferral_reason"))
            if not (built or deferred or e.get("parity_status") == "superseded"):
                unresolved.append(e.get("legacy_path"))
    assert not unresolved, f"P1 entries neither built nor deferred-with-reason: {unresolved}"
