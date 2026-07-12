# URN: test:validate-conventions:p0-graph-integrity-variants:E013-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E013-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E013
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E013 — no target variant imports a legacy persona validator module"""
from __future__ import annotations

from pathlib import Path

import yaml

def test_variants_do_not_import_legacy(conventions_dir: Path) -> None:
    variants = [p for p in conventions_dir.glob("*/test_*.py") if p.parent.name != "tests"]
    assert variants, "no convention validator variants implemented yet"
    offenders = []
    for p in variants:
        txt = p.read_text(encoding="utf-8")
        if "atdd.planner.validators" in txt or "atdd.tester.validators" in txt \
           or "atdd.coder.validators" in txt or "atdd.coach.validators" in txt:
            offenders.append(p.name)
    assert not offenders, f"variants importing legacy persona validators: {offenders}"
