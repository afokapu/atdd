# URN: test:validate-conventions:legacy-decommission:Y001-SMOKE-001-seed
# Acceptance: acc:validate-conventions:Y001-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:Y001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""Y001 — no legacy validator is deleted without a safe parity status and an existing target"""
from __future__ import annotations

from pathlib import Path

import yaml

SAFE = {"direct","split","merged","superseded"}
LEGACY_ROOTS = ["src/atdd/planner/validators","src/atdd/tester/validators","src/atdd/coder/validators","src/atdd/coach/validators"]

def test_no_unsafe_legacy_deletion(repo_root: Path) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    entries = {}
    if map_path.exists():
        doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
        entries = {e.get("legacy_path"): e for e in (doc.get("entries") or [])}
    unsafe = []
    for path, e in entries.items():
        present = (repo_root / path).exists() if path else True
        if present:
            continue  # not deleted -> safe
        status = e.get("parity_status")
        tgt = e.get("proposed_target_path")
        if status not in SAFE or not (tgt and (repo_root / tgt).exists()):
            unsafe.append(f"{path}: deleted with status={status}, target={tgt}")
    assert not unsafe, f"legacy validators unsafely deleted: {unsafe}"
