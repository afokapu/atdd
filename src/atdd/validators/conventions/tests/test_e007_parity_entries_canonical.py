# URN: test:validate-conventions:legacy-parity-audit:E007-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E007-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E007 — every parity entry uses a canonical family/template from the #1204 registry"""
from __future__ import annotations

from pathlib import Path

import yaml

def test_entries_use_canonical_families_and_templates(repo_root: Path, canonical_templates: dict) -> None:
    map_path = repo_root / "docs" / "validator-parity" / "legacy-validator-map.yaml"
    assert map_path.exists(), f"parity map not found at {map_path}"
    doc = yaml.safe_load(map_path.read_text(encoding="utf-8")) or {}
    valid_pairs = {(fam, t) for fam, ts in canonical_templates.items() for t in ts}
    bad = []
    for e in (doc.get("entries") or []):
        fam, tmpl = e.get("proposed_family"), e.get("proposed_template")
        if fam in ("non_convention","extension_candidate") or tmpl is None:
            continue
        if (fam, tmpl) not in valid_pairs:
            bad.append(f"{e.get('legacy_path')}: ({fam},{tmpl})")
    assert not bad, f"entries with non-canonical family/template: {bad}"
