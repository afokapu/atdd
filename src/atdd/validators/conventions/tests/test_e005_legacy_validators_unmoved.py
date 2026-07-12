# URN: test:validate-conventions:registry-archetype-conformance:E005-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E005-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E005
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E005 — legacy persona validator folders remain present and unmoved (regression guard)."""
from __future__ import annotations

from pathlib import Path

LEGACY_VALIDATOR_ROOTS = [
    "src/atdd/planner/validators",
    "src/atdd/tester/validators",
    "src/atdd/coder/validators",
    "src/atdd/coach/validators",
]


def test_legacy_validator_folders_are_unmoved(repo_root: Path) -> None:
    missing = [r for r in LEGACY_VALIDATOR_ROOTS if not (repo_root / r).is_dir()]
    assert not missing, (
        f"legacy persona validator folders moved or deleted: {missing} — "
        "the convention suite must run in parallel, not replace legacy in #1204"
    )
    # Each legacy root must still hold executable validators (non-empty).
    empty = [
        r
        for r in LEGACY_VALIDATOR_ROOTS
        if not list((repo_root / r).glob("test_*.py"))
    ]
    assert not empty, f"legacy validator folders unexpectedly empty: {empty}"
