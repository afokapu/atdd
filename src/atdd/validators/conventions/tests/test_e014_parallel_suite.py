# URN: test:validate-conventions:p1-parity-variants:E014-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E014-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E014
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E014 — the convention variant suite is collectable in parallel with legacy"""
from __future__ import annotations

from pathlib import Path

import yaml

def test_convention_variant_suite_exists(conventions_dir: Path) -> None:
    variants = list(conventions_dir.glob("*/test_*.py"))
    assert variants, (
        "no convention variant suite to run in parallel with legacy yet "
        "(target conventions/<family>/test_<variant>.py files absent)"
    )
