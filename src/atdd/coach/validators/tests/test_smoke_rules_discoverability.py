# Acceptance: acc:govern-lifecycle:E003-UNIT-001-rules-grep-finds-both-new-rules
# Acceptance: acc:govern-lifecycle:E003-UNIT-002-rules-show-resolves-each-rule
# Acceptance: acc:govern-lifecycle:E003-SMOKE-002-rules-grep-finds-both-new-rules
# Acceptance: acc:govern-lifecycle:E003-SMOKE-003-rules-show-resolves-each-rule
"""
Rules-discovery anchor tests for the substrate SMOKE+REFACTOR phase
enforcement rules (issue #681).

The 2026-05-13 substrate-asymmetry incident shipped 8 PRs through
auto-close at atdd:GREEN because the lifecycle's SMOKE phase enforcement
existed only as prose in CLAUDE.md. The mechanical fix introduced two
new rules:

  - planner.wmbt.must-have-smoke-acceptance  (suppress-and-clean, sev 3)
  - coach.pr.merge-blocks-on-pre-smoke-close (strict, sev 4)

These tests anchor the substrate-discovery acceptances from
``plan/govern_lifecycle/E003.yaml``: every authoring agent's `atdd rules
grep` / `atdd rules show` workflow must surface both rule_ids, and
``bind_rule()`` must resolve each from the merged convention registry.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_binding import (
    AmbiguousRuleError,
    RuleNotInRegistryError,
    bind_rule,
    iter_rules,
)


_NEW_RULE_IDS = (
    "planner.wmbt.must-have-smoke-acceptance",
    "coach.pr.merge-blocks-on-pre-smoke-close",
)


@pytest.mark.parametrize("rule_id", _NEW_RULE_IDS)
def test_iter_rules_surfaces_new_smoke_rules(rule_id):
    """
    E003-UNIT-001 + E003-SMOKE-002: ``atdd rules grep`` walks the same
    registry ``iter_rules()`` exposes — confirming the iterator surfaces
    each new rule_id certifies the rule is reachable from the CLI.
    """
    canonical_ids = {r.rule_id for r in iter_rules()}
    assert rule_id in canonical_ids, (
        f"Rule {rule_id!r} not found by iter_rules(); "
        f"atdd rules grep would not surface it. "
        f"Check that the rule is declared under `rules:` in its convention YAML."
    )


@pytest.mark.parametrize("rule_id", _NEW_RULE_IDS)
def test_bind_rule_resolves_new_smoke_rules(rule_id):
    """
    E003-UNIT-002 + E003-SMOKE-003: ``atdd rules show <rule-id>`` calls
    ``bind_rule()`` to render metadata — confirming bind_rule resolves
    each rule certifies the CLI's --show path works end-to-end.
    """
    try:
        meta = bind_rule(rule_id)
    except RuleNotInRegistryError as exc:
        pytest.fail(f"bind_rule({rule_id!r}) raised RuleNotInRegistryError: {exc}")
    except AmbiguousRuleError as exc:
        pytest.fail(f"bind_rule({rule_id!r}) raised AmbiguousRuleError: {exc}")

    # Sanity: the resolved metadata carries the expected fields the CLI
    # prints under `atdd rules show`.
    assert meta.rule_id == rule_id
    assert isinstance(meta.severity, int) and 1 <= meta.severity <= 5
    assert meta.disposition in {
        "strict", "suppress-and-clean", "advisory", "documentation-only",
    }
    assert meta.description, "rule must declare a non-empty description"


def test_disposition_matches_substrate_design():
    """The two new rules carry the dispositions called out in #681:

    - planner.wmbt.must-have-smoke-acceptance → suppress-and-clean
      (docs-only WMBTs inline-suppress with deadline)
    - coach.pr.merge-blocks-on-pre-smoke-close → strict
      (merge gate is a hard substrate boundary; no per-PR bypass)
    """
    planner_meta = bind_rule("planner.wmbt.must-have-smoke-acceptance")
    coach_meta = bind_rule("coach.pr.merge-blocks-on-pre-smoke-close")

    assert planner_meta.disposition == "suppress-and-clean", (
        f"planner rule disposition drift — expected suppress-and-clean, "
        f"got {planner_meta.disposition!r}"
    )
    assert coach_meta.disposition == "strict", (
        f"coach rule disposition drift — expected strict, "
        f"got {coach_meta.disposition!r}"
    )
