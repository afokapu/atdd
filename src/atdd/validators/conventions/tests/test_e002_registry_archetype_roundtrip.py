# URN: test:validate-conventions:registry-archetype-conformance:E002-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E002-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E002 — each family archetype.py exposes exactly its registry-assigned template ids."""
from __future__ import annotations

import importlib
from pathlib import Path

import yaml


def test_registry_and_archetype_exports_agree(conventions_dir: Path) -> None:
    registry_path = conventions_dir / "registry.yaml"
    assert registry_path.exists(), f"registry not found at {registry_path}"

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    families = registry.get("families") or []
    assert families, "registry declares no families"

    mismatches: list[str] = []
    for fam in families:
        fid = fam.get("id")
        registry_ids = sorted(t.get("id") for t in (fam.get("templates") or []))
        mod = importlib.import_module(f"atdd.validators.conventions.{fid}.archetype")
        exported = getattr(mod, "TEMPLATES", None)
        if exported is None:
            mismatches.append(f"{fid}: archetype exposes no TEMPLATES")
            continue
        archetype_ids = sorted(
            t["template_id"] if isinstance(t, dict) else getattr(t, "template_id")
            for t in exported
        )
        if archetype_ids != registry_ids:
            mismatches.append(f"{fid}: archetype {archetype_ids} != registry {registry_ids}")

    assert not mismatches, f"registry<->archetype divergence: {mismatches}"
