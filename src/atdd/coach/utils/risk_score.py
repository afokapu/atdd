# URN: component:govern-lifecycle:enforcement-substrate:RiskScoreBreakdown:backend:application
# Runtime: python
# Purpose: Slice the risk score (sum of severity over active violations) by archetype.

"""
Risk-score archetype breakdown.

Coach v6 §6.8 defines the risk score as ``sum(v.severity for v in violations)``.
Substrate spec v12 §8.3 splits that scalar into per-archetype slices so a PR
reader can tell at a glance whether outstanding debt is in toolkit conventions
(``coder|coach|tester|planner``) or in repo acceptances/security (``repo``).

Slice granularity is one bucket per archetype — per-wagon or per-rule sub-slices
are deliberately out of scope (substrate spec §8.3, issue #418). The ``repo``
slice mixes acceptance-derived rules (constant severity 4 per §4.2) with
security-derived rules (low→2 / medium→3 / high→4 / critical→5 per §4.2); no
severity filtering happens inside the slice.

This module is a pure aggregation utility — it does not run validators or
discover violations. Callers pass an already-collected ``list[Violation]``.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from atdd.coach.validators._violation import Violation


# Canonical archetype set. Mirrors:
#   - src/atdd/coach/specs/rule-id.spec.md (SPEC-COACH-RULEID-0002)
#   - src/atdd/coach/conventions/rule-id.convention.yaml::archetype enum
ARCHETYPES: tuple[str, ...] = ("coder", "coach", "tester", "planner", "repo")


def compute_risk_breakdown(
    violations: Iterable[Violation],
) -> Dict[str, int]:
    """Return per-archetype severity sums.

    Iterates ``violations`` once, grouping by the leading dotted segment of
    ``rule_id`` (the archetype). Every archetype in :data:`ARCHETYPES` is
    present in the result, defaulting to ``0`` when no violations contributed.

    Violations whose ``rule_id`` has an unknown leading segment are silently
    ignored — the rule-ID grammar validator (``coach.rule-id.*``) is the gate
    for invalid archetypes; double-flagging here would just duplicate noise.
    """
    breakdown: Dict[str, int] = {arch: 0 for arch in ARCHETYPES}
    for v in violations:
        archetype, _, _ = v.rule_id.partition(".")
        if archetype in breakdown:
            breakdown[archetype] += v.severity
    return breakdown


def format_risk_breakdown_section(breakdown: Dict[str, int]) -> str:
    """Render the breakdown as a Markdown PR-description section.

    The section header is ``## Risk score breakdown`` (substrate spec §8.3 +
    issue #418). The body is a two-column table — archetype, severity sum —
    plus a total line so a reader can verify the slice-sum invariant at a
    glance. Toolkit slices and the ``repo`` slice are emitted in canonical
    archetype order.
    """
    lines: List[str] = []
    lines.append("## Risk score breakdown")
    lines.append("")
    lines.append("| Archetype | Severity sum |")
    lines.append("|-----------|--------------|")
    for arch in ARCHETYPES:
        lines.append(f"| {arch} | {breakdown.get(arch, 0)} |")
    total = sum(breakdown.get(arch, 0) for arch in ARCHETYPES)
    lines.append(f"| **total** | **{total}** |")
    return "\n".join(lines)


__all__ = [
    "ARCHETYPES",
    "compute_risk_breakdown",
    "format_risk_breakdown_section",
]
