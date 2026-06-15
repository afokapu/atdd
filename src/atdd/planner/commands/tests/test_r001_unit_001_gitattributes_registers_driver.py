# URN: test:author-atdd-substrate:author-merge-driver:R001-UNIT-001-gitattributes-registers-driver
# Acceptance: acc:author-atdd-substrate:R001-UNIT-001-gitattributes-registers-driver
# WMBT: wmbt:author-atdd-substrate:R001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""R001-UNIT-001 — the .gitattributes wiring registers the driver for registries."""
from __future__ import annotations

from atdd.planner.commands.author_registry import MERGE_DRIVER_NAME, gitattributes_lines


def test_gitattributes_register_registry_files():
    lines = gitattributes_lines()
    joined = "\n".join(lines)
    assert f"merge={MERGE_DRIVER_NAME}" in joined
    assert "relationships.yaml" in joined
    assert "scopes.yaml" in joined
    assert "gates" in joined  # per-trigger gate files
