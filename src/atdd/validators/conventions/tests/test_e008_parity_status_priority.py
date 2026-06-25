# URN: test:validate-conventions:legacy-parity-audit:E008-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E008-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E008
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E008 — every parity entry has a valid status and priority"""
from __future__ import annotations

from pathlib import Path

import yaml

VALID_STATUSES = {'direct','split','merged','superseded','extension_candidate','not_convention_graph','needs_design'}
VALID_PRIORITIES = {'P0','P1','P2'}

def test_entries_have_valid_status_and_priority(repo_root: Path) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    assert map_path.exists(), f"parity map not found at {map_path}"
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    bad = []
    for e in (doc.get("entries") or []):
        if e.get("parity_status") not in VALID_STATUSES or e.get("priority") not in VALID_PRIORITIES:
            bad.append(f"{e.get('legacy_path')}: status={e.get('parity_status')} priority={e.get('priority')}")
    assert not bad, f"entries with invalid status/priority: {bad}"
