# URN: test:author-atdd-substrate:author-issue-body:E012-REFACTOR-001-guard-name-matches-what-it-compares
# Acceptance: acc:author-atdd-substrate:E012-REFACTOR-001-guard-name-matches-what-it-compares
# WMBT: wmbt:author-atdd-substrate:E012
# Phase: REFACTOR
# Layer: application
"""E012-REFACTOR-001 — the guard may claim only the surfaces it compares.

Not cosmetics. "Tri-directional" is the reason the gap survived: a name that asserts
three surfaces tells every reader the third is covered, so nobody goes looking. The
guard has compared two for subsections since #682 lifted the H3s to mandatory, and
the only thing standing in for the third was a literal in the test helper that
restated the first — a copy of the schema wearing the template's job.

So this is the acceptance that keeps the fix honest once #1978 lands: if the module
still claims to be tri-directional, it must actually perform the template arm.

PHASE: REFACTOR, deliberately. It will fail through RED and GREEN, which is correct
— the claim cannot be made true until the arm from C011-UNIT-002 exists and the
naming follows it. Satisfying it earlier would mean renaming before fixing, which is
the same trade in the opposite direction.
"""
from __future__ import annotations

from pathlib import Path

_TESTS_DIR = Path(__file__).parent

#: The token that asserts three surfaces.
_TRI_CLAIM = "tri-directional"

#: The arm whose presence makes that claim true for subsections.
_TEMPLATE_ARM = "template_missing_required_subsections"


def _guard_modules() -> list[Path]:
    """Every C011 guard module — the unit and the live smoke."""
    found = sorted(_TESTS_DIR.glob("test_c011_*drift_guard*.py"))
    assert found, "no C011 drift-guard module found; has it been renamed?"
    return found


def test_the_template_arm_is_performed_by_the_guard():
    """The third surface is compared somewhere in the C011 guard, not just described."""
    performed = [p.name for p in _guard_modules() if _TEMPLATE_ARM in p.read_text(encoding="utf-8")]
    assert performed, (
        f"no C011 guard module calls {_TEMPLATE_ARM}() — the schema-H3-versus-template "
        f"comparison is still unperformed, so the guard compares two surfaces for "
        f"subsections. #1978 Phase 2 (GREEN) lands the arm; this acceptance holds the "
        f"name to it."
    )


def test_a_module_claiming_tri_directional_actually_compares_three():
    """The claim and the code must agree — either perform the arm, or stop claiming it."""
    for path in _guard_modules():
        text = path.read_text(encoding="utf-8")
        claims = _TRI_CLAIM in text.lower() or _TRI_CLAIM.replace("-", "_") in path.name.lower()
        if not claims:
            continue
        assert _TEMPLATE_ARM in text, (
            f"{path.name} claims {_TRI_CLAIM!r} but never calls {_TEMPLATE_ARM}(); "
            f"a name that asserts a comparison it does not make is how this gap "
            f"survived. Perform the arm, or drop the claim from the name and docstring."
        )
