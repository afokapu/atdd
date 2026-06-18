# URN: test:author-plan-substrate:author-wmbt:E003-UNIT-001-odi-file-with-seed-smoke
# Acceptance: acc:author-plan-substrate:E003-UNIT-001-odi-file-with-seed-smoke
# WMBT: wmbt:author-plan-substrate:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E003-UNIT-001 (plan wmbt) — create_wmbt writes an ODI file carrying a seed SMOKE acceptance.

RED: create_wmbt does not exist yet.
"""
from __future__ import annotations

import yaml

from atdd.planner.commands.author import create_wmbt


def test_create_wmbt_writes_odi_with_seed_smoke(tmp_path):
    spec = {
        "wagon_slug": "demo-wagon",
        "code": "E001",
        "step": "execute",
        "direction": "maximize",
        "dimension": "likelihood",
        "object_of_control": "thing-creation",
        "context_clarifier": "when doing the thing, the writer creates a file",
        "lens": "functional.effectiveness",
        "statement": "maximize likelihood of thing-creation when authoring the thing",
    }
    path = create_wmbt(spec, root=tmp_path)
    assert path == tmp_path / "plan" / "demo_wagon" / "E001.yaml"
    doc = yaml.safe_load(path.read_text())
    phases = [a["identity"]["phase"] for a in doc.get("acceptances", [])]
    assert "SMOKE" in phases  # must-have-smoke holds by construction
