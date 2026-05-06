# URN: component:govern-lifecycle:enforcement-substrate:risk_score:backend:tests
# Runtime: python
# Purpose: Cover the per-archetype risk-score breakdown defined in §8.3 (issue #418).

"""
Unit tests for ``atdd.coach.utils.risk_score``.

Exercises substrate spec v12 §8.3 — the breakdown dict must contain a key per
archetype (``coder``, ``coach``, ``tester``, ``planner``, ``repo``) with the
sum of severities of violations whose ``rule_id`` starts with that archetype.
"""

from __future__ import annotations

import pytest

from atdd.coach.utils.risk_score import (
    ARCHETYPES,
    compute_risk_breakdown,
    format_risk_breakdown_section,
)
from atdd.coach.validators._violation import Violation


def _v(rule_id: str, severity: int, location: str = "x.py:1") -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=severity,
        location=location,
        detail="fixture",
    )


# ---------------------------------------------------------------------------
# AC #1 — mixed archetypes produce a breakdown with all canonical keys
# ---------------------------------------------------------------------------


def test_breakdown_has_all_canonical_keys_with_severity_sums():
    """AC #1 from issue #418.

    A Violation list with mixed archetypes (``coder.*``, ``tester.*``,
    ``repo.*``) yields a dict whose keys are exactly the canonical archetype
    set and whose values sum severities per archetype.
    """
    violations = [
        _v("coder.dead-code.unreachable-definitions", 3),
        _v("coder.boundaries.cross-wagon-import", 2),
        _v("tester.smoke.harness-subprocess-failed-crash", 4),
        _v("repo.acceptance.ledger-shape", 4),
        _v("repo.security.session-token-storage", 5),
    ]

    breakdown = compute_risk_breakdown(violations)

    assert set(breakdown.keys()) == {"coder", "coach", "tester", "planner", "repo"}
    assert breakdown["coder"] == 5
    assert breakdown["coach"] == 0
    assert breakdown["tester"] == 4
    assert breakdown["planner"] == 0
    assert breakdown["repo"] == 9


# ---------------------------------------------------------------------------
# Empty input — every archetype slice is zero, never missing
# ---------------------------------------------------------------------------


def test_breakdown_empty_violations_returns_all_zero_slices():
    """No violations still yields the full archetype set (zeros).

    Downstream renderers should be able to assume every key is present;
    forcing them to use ``.get(arch, 0)`` would invite ``KeyError``s when
    the renderer adds a new archetype mid-flight.
    """
    breakdown = compute_risk_breakdown([])

    assert breakdown == {arch: 0 for arch in ARCHETYPES}


# ---------------------------------------------------------------------------
# repo slice mixes acceptance- and security-derived rules without filtering
# ---------------------------------------------------------------------------


def test_repo_slice_mixes_acceptance_and_security_severities():
    """§4.2: acceptance rules are constant severity 4; security rules map
    low→2 / medium→3 / high→4 / critical→5. The repo slice must sum across
    both kinds without filtering.
    """
    violations = [
        _v("repo.acceptance.foo", 4),
        _v("repo.acceptance.bar", 4),
        _v("repo.security.low", 2),
        _v("repo.security.medium", 3),
        _v("repo.security.high", 4),
        _v("repo.security.critical", 5),
    ]

    breakdown = compute_risk_breakdown(violations)

    assert breakdown["repo"] == 4 + 4 + 2 + 3 + 4 + 5
    assert breakdown["coder"] == 0


# ---------------------------------------------------------------------------
# Total-of-slices invariant — substrate spec §8.3
# ---------------------------------------------------------------------------


def test_breakdown_slices_sum_to_total_severity():
    """Coach v6 §6.8 risk score = sum of severity over all violations. The
    archetype slices must partition that scalar — no severity is double-counted
    or dropped.
    """
    violations = [
        _v("coder.green.x", 1),
        _v("coach.rule-id.y", 2),
        _v("tester.smoke.z", 3),
        _v("planner.criteria.w", 4),
        _v("repo.acceptance.u", 4),
    ]

    breakdown = compute_risk_breakdown(violations)
    total = sum(breakdown.values())

    assert total == sum(v.severity for v in violations)


# ---------------------------------------------------------------------------
# Unknown archetype prefix — silently ignored, not raised
# ---------------------------------------------------------------------------


def test_unknown_archetype_prefix_is_ignored():
    """An unknown leading segment is skipped — the rule-ID grammar validator
    is the gate for invalid archetypes, double-flagging here would just
    duplicate noise.
    """
    violations = [
        _v("coder.green.x", 3),
        _v("legacy.foo.bar", 5),  # leading segment is not a canonical archetype
    ]

    breakdown = compute_risk_breakdown(violations)

    assert breakdown["coder"] == 3
    assert all(arch in breakdown for arch in ARCHETYPES)
    assert "legacy" not in breakdown


# ---------------------------------------------------------------------------
# Markdown rendering — section header + table + total
# ---------------------------------------------------------------------------


def test_format_section_emits_canonical_markdown():
    """The PR-description section must use the exact header "## Risk score
    breakdown" (substrate spec §8.3 + issue #418) and list every archetype
    slice plus a total row.
    """
    breakdown = compute_risk_breakdown(
        [
            _v("coder.green.x", 1),
            _v("repo.acceptance.y", 4),
        ]
    )

    section = format_risk_breakdown_section(breakdown)

    assert section.startswith("## Risk score breakdown")
    assert "| Archetype | Severity sum |" in section
    for arch in ARCHETYPES:
        assert f"| {arch} |" in section
    assert "**total**" in section
    assert "**5**" in section


# ---------------------------------------------------------------------------
# Empty section still renders — the substrate is present even with no debt
# ---------------------------------------------------------------------------


def test_format_section_renders_zero_breakdown():
    section = format_risk_breakdown_section(compute_risk_breakdown([]))

    assert "## Risk score breakdown" in section
    for arch in ARCHETYPES:
        assert f"| {arch} | 0 |" in section
    assert "**total**" in section
    assert "**0**" in section


# ---------------------------------------------------------------------------
# Iterable input — generators work as well as lists
# ---------------------------------------------------------------------------


def test_breakdown_accepts_generator():
    def gen():
        yield _v("coder.x.y", 2)
        yield _v("repo.x.y", 3)

    breakdown = compute_risk_breakdown(gen())

    assert breakdown["coder"] == 2
    assert breakdown["repo"] == 3
