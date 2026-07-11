# URN: test:validate-conventions:p0-graph-integrity-variants:E010-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E010-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E010
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E010 — every convention variant that exists is a built, executing variant.

Map-free: the parity map under ``docs/validator-parity/`` is retired with the rest of the
migration scaffolding, so this no longer asks "does every P0 map entry have a target
file?". It asks the surviving, stronger question directly of the tree: every convention
variant module under a family directory must EXECUTE — carry ``# Phase: GREEN`` and define
a real test function — so an unbuilt or stubbed-out P0 variant cannot sit in the tree
passing vacuously.
"""
from __future__ import annotations

import re
from pathlib import Path

CONV_REL = "src/atdd/validators/conventions"

# Sibling dirs of the convention families: harness/support, not variants.
NON_FAMILY_DIRS = {"tests", "_support", "__pycache__"}

# ``*_variant_contract`` is the contract test every variant carries; the richer parity
# variants add fault/parity/catches tests on top. Mirrors ``_variant_executes`` in
# tests/test_y003_sweep_coverage_guards.py, widened to the whole population.
_EXECUTES = re.compile(r"def test_\w*(fault|parity|catches|convention|legacy|variant_contract)")


def _family_dirs(conv: Path) -> list[Path]:
    return sorted(
        d for d in conv.iterdir()
        if d.is_dir() and d.name not in NON_FAMILY_DIRS and not d.name.startswith(".")
    )


def _variant_executes(vf: Path) -> bool:
    if not vf.exists():
        return False
    txt = vf.read_text(encoding="utf-8")
    if "# Phase: GREEN" not in txt:
        return False
    return bool(_EXECUTES.search(txt))


def test_p0_variants_are_built_and_execute(repo_root: Path) -> None:
    conv = repo_root / CONV_REL
    assert conv.is_dir(), f"conventions tree not found at {conv}"

    variants = [f for d in _family_dirs(conv) for f in sorted(d.glob("test_*.py"))]
    assert variants, f"no convention variants discovered under {conv}"

    unbuilt = [
        str(f.relative_to(conv)) for f in variants if not _variant_executes(f)
    ]
    assert not unbuilt, (
        "convention variants that do not execute (missing '# Phase: GREEN' or a real "
        f"test function): {unbuilt}"
    )
