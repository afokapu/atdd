# URN: test:validate-conventions:family-template-catalogue:E001-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E001-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001 — registry.yaml declares exactly the 13 canonical families and 24 templates.

The catalogue grew from 22 to 24 when the train-interlocking sanity rules (#1249,
parent #1246) added ``schema/required_field_presence`` (entrypoint-shape presence)
and ``coverage/projection_covers_source`` (route->train projection coverage)."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_registry_declares_canonical_families_and_templates(
    conventions_dir: Path, canonical_families: list, canonical_templates: dict
) -> None:
    registry_path = conventions_dir / "registry.yaml"
    assert registry_path.exists(), f"registry not found at {registry_path}"

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    families = registry.get("families") or []
    family_ids = [f.get("id") for f in families]

    assert family_ids == canonical_families, (
        f"registry families {family_ids} != canonical {canonical_families}"
    )

    total_templates = 0
    for fam in families:
        fid = fam.get("id")
        got = [t.get("id") for t in (fam.get("templates") or [])]
        assert got == canonical_templates[fid], (
            f"family '{fid}' templates {got} != {canonical_templates[fid]}"
        )
        total_templates += len(got)

    assert len(family_ids) == 13, f"expected 13 families, got {len(family_ids)}"
    assert total_templates == 24, f"expected 24 templates, got {total_templates}"
