# URN: test:govern-registry:E003-UNIT-003-a-rule-nested-in-a-monolith-is-part-of-the-measured-surface
# Acceptance: acc:govern-registry:E003-UNIT-003-a-rule-nested-in-a-monolith-is-part-of-the-measured-surface
# WMBT: wmbt:govern-registry:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E003-UNIT-003-a-rule-nested-in-a-monolith-is-part-of-the-measured-surface.

The measured core surface is walked by the shipped rule walker, so a rule declared
in a nested ``rules:`` list inside a monolith is held to the same coverage obligation
as a top-level one. A depth-1 reader sees only the top-level list, silently shrinks
the surface, and then reports coverage over a subset while calling it the whole —
which is how the corpus came to be understated in #1969.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.twin_coverage import (
    core_coder_tester_surface,
    measure_twin_coverage,
    why_not_verdicts,
)

_TOP_LEVEL = "coder.logging.top-level-declaration"
_NESTED = "coder.logging.nested-declaration"

# Two declarations, one nesting level apart. The nested list under canonical_rules
# reproduces the real shape in src/atdd/coder/conventions/logging.convention.yaml.
_MONOLITH = f"""\
version: '1.0'
name: Logging Convention
rules:
  - id: {_TOP_LEVEL}
    severity: 2
    disposition: documentation-only
    description: declared in the top-level rules list
canonical_rules:
  rules:
    - id: {_NESTED}
      severity: 2
      disposition: documentation-only
      description: declared one level deeper, invisible to a depth-1 reader
"""


def test_a_rule_nested_in_a_monolith_is_part_of_the_measured_surface(tmp_path: Path) -> None:
    conventions = tmp_path / "src" / "atdd" / "coder" / "conventions"
    conventions.mkdir(parents=True)
    (conventions / "logging.convention.yaml").write_text(_MONOLITH, encoding="utf-8")

    surface = core_coder_tester_surface(tmp_path)

    # Both are members of the measured surface — the nested one is not invisible.
    assert set(surface) == {_TOP_LEVEL, _NESTED}

    # No extension node mirrors either, and no verdict classifies either.
    coverage = measure_twin_coverage(
        surface, twins={}, why_not=why_not_verdicts(tmp_path / "absent.md")
    )

    # Both carry the same coverage obligation.
    assert coverage.uncovered == (_NESTED, _TOP_LEVEL)

    # And the reported surface size counts the nested rule, so the shortfall cannot
    # be understated by omitting it.
    assert len(coverage.core_surface) == 2
    assert coverage.move_ready is False
