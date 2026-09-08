# URN: component:govern-lifecycle:bind-issue-feature:FeatureBindingValidator:backend:tests
# Purpose: Enforce coach.issue.feature-binding-must-resolve (#1635) — an issue's
#          declared feature must resolve in plan/, and the body and the store
#          must agree.
"""coach.issue.feature-binding-must-resolve validator (#1635).

Scans the local State Store: every issue-backed work item's declared feature must
resolve to a real feature YAML under ``plan/``, and the body's ``Feature`` row
must agree with the stored field.

Deliberately carries NO marker. `atdd validate coach --local --skip-api` selects
``-m "(not github_api) and (not platform)"``, so a ``platform``-marked validator
is silently deselected by the very gate that is supposed to run it — during this
issue's own planner pass the mandated gate reported 211 passed while the full
directory was red. This validator reads the store and ``plan/`` off disk and
makes no provider call, so it needs neither marker and the gate cannot skip it.

Disposition is ``advisory`` while the pre-existing backlog is cleared (638 of 808
work items carried no feature when measured on 2026-07-28). Escalate the node's
disposition once the backfill has run and the unresolved set is empty.

Rule: coach.issue.feature-binding-must-resolve
Run:  atdd validate coach
"""
from __future__ import annotations

from typing import List

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.validators.issue_feature_binding_scanner import (
    _RULE, scan_feature_bindings, scan_store_bindings,
)

_VALIDATOR_ID = "test_issue_feature_binding"
_RULE_ID = "coach.issue.feature-binding-must-resolve"


def _scan_live() -> List[Violation]:
    try:
        return scan_store_bindings(find_repo_root())
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        # An unreachable store must not break the gate; the store-health
        # validators own that failure mode.
        return []


def test_rule_is_bound() -> None:
    """The bidirectional binding contract (SPEC-COACH-RULEID-0007)."""
    assert bind_rule(_RULE_ID).rule_id == _RULE_ID
    assert _RULE.rule_id == _RULE_ID


def test_scanner_reports_a_non_resolving_binding() -> None:
    """Fault control: the scan must be able to fail, or it enforces nothing."""
    violations = scan_feature_bindings(
        [{"number": 1, "feature": "feature:govern-lifecycle:no-such-feature", "body": ""}],
        plan_root=find_repo_root(),
    )
    assert violations, "the scanner passed a feature URN that resolves to nothing"
    assert violations[0].rule_id == _RULE.rule_id


def test_feature_bindings_resolve() -> None:
    """Every issue-backed work item's feature must resolve against plan/.

    ``bind_rule`` is called here, not merely at module import, because
    ``coach.rule.validator-binding`` resolves the rule's declared validator and
    requires THAT function body to name the rule it enforces — a module-level
    binding read through an import is invisible to it.
    """
    rule = bind_rule(_RULE_ID)
    assert rule.rule_id == _RULE_ID
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())
