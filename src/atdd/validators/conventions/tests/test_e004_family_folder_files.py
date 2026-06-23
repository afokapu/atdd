# URN: test:validate-conventions:family-template-catalogue:E004-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E004-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E004 — every family folder contains README.md, archetype.py and fixtures.py."""
from __future__ import annotations

from pathlib import Path

REQUIRED_FILES = ["README.md", "archetype.py", "fixtures.py"]


def test_every_family_folder_has_required_files(
    conventions_dir: Path, canonical_families: list
) -> None:
    missing: list[str] = []
    for family in canonical_families:
        family_dir = conventions_dir / family
        for fname in REQUIRED_FILES:
            if not (family_dir / fname).exists():
                missing.append(f"{family}/{fname}")
    assert not missing, f"missing required family files: {missing}"
