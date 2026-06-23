# URN: test:validate-conventions:shadow-and-promote:E018-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E018-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E018
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E018 — the convention validators are promoted to the authoritative validation path"""
from __future__ import annotations

from pathlib import Path

import yaml

def test_conventions_are_authoritative(repo_root: Path) -> None:
    marker = repo_root / "src" / "atdd" / "validators" / "conventions" / "AUTHORITATIVE"
    cfg = repo_root / ".atdd" / "config.yaml"
    promoted = marker.exists()
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        promoted = promoted or bool((data.get("validators") or {}).get("conventions_authoritative"))
    assert promoted, "convention validators not yet promoted to the authoritative path"
