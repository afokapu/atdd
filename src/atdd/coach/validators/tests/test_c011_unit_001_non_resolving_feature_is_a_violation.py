# URN: test:govern-lifecycle:bind-issue-feature:C011-UNIT-001-non-resolving-feature-is-a-violation
# Acceptance: acc:govern-lifecycle:C011-UNIT-001-non-resolving-feature-is-a-violation
# WMBT: wmbt:govern-lifecycle:C011
# Phase: RED
# Layer: domain
# Runtime: python
# Assertion: behavioral
# Purpose: The validator distinguishes no binding, a malformed binding, and a well-formed binding naming a feature plan/ does not contain — reporting each with the issue and URN named.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:C011-UNIT-001-non-resolving-feature-is-a-violation
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:C011

Purpose: a declared feature URN must be held to resolving against plan/.

The body's Feature row and the store's work_item.data.feature are both
unvalidated today, so a train URN wearing a feature's clothes passes unnoticed.
Measured 2026-07-28: #1626 declares a train identity, and #1635 itself carries
an unrelated feature about manifest commits.

The scanner does not exist yet. It is resolved dynamically so its absence reads
as a behavioural assertion naming the missing surface.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    ABSENT_FEATURE_URN,
    FEATURE_URN,
    TRAIN_URN_IN_FEATURE_SLOT,
    control_root,
    optional_attr,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_SCANNER_MODULE = "atdd.coach.validators.issue_feature_binding_scanner"
_SCANNER_ATTR = "scan_feature_bindings"
_RULE_ID = "coach.issue.feature-binding-must-resolve"

BOUND = 94001
TRAIN_DRIFT = 94002
ABSENT = 94003
UNBOUND = 94004


def _scanner():
    fn = optional_attr(_SCANNER_MODULE, _SCANNER_ATTR)
    assert fn is not None, (
        f"no feature-binding scanner: expected {_SCANNER_MODULE}.{_SCANNER_ATTR}. "
        "Nothing currently holds an issue's declared feature to resolving "
        "against plan/, so drift is invisible."
    )
    return fn


@pytest.fixture()
def plan_root(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root)
    return root


def _issues():
    return [
        {"number": BOUND, "feature": FEATURE_URN,
         "body": f"| Feature | `{FEATURE_URN}` |"},
        {"number": TRAIN_DRIFT, "feature": TRAIN_URN_IN_FEATURE_SLOT,
         "body": f"| Feature | `{TRAIN_URN_IN_FEATURE_SLOT}` |"},
        {"number": ABSENT, "feature": ABSENT_FEATURE_URN,
         "body": f"| Feature | `{ABSENT_FEATURE_URN}` |"},
        {"number": UNBOUND, "feature": None, "body": "no Feature row at all"},
    ]


def _for_issue(violations, number):
    return [v for v in violations if str(number) in str(getattr(v, "location", ""))]


def test_a_resolving_binding_produces_no_violation(plan_root) -> None:
    violations = _scanner()(_issues(), plan_root=plan_root)
    assert _for_issue(violations, BOUND) == [], (
        "a feature that resolves in plan/ was reported as a violation"
    )


def test_a_train_urn_is_reported_as_not_a_feature_identity(plan_root) -> None:
    violations = _scanner()(_issues(), plan_root=plan_root)
    reported = _for_issue(violations, TRAIN_DRIFT)
    assert reported, "a train URN in the Feature slot passed unreported (#1626 drift)"
    assert any("feature" in str(getattr(v, "detail", "")).lower() for v in reported), (
        "the violation does not say the declared value is not a feature identity"
    )


def test_a_well_formed_but_absent_feature_is_reported_with_its_urn(plan_root) -> None:
    violations = _scanner()(_issues(), plan_root=plan_root)
    reported = _for_issue(violations, ABSENT)
    assert reported, "a feature URN absent from plan/ passed unreported"
    assert any(ABSENT_FEATURE_URN in str(getattr(v, "detail", "")) for v in reported), (
        "the violation does not name the URN that resolved to nothing"
    )


def test_an_unbound_issue_is_reported_rather_than_passing_by_default(plan_root) -> None:
    violations = _scanner()(_issues(), plan_root=plan_root)
    assert _for_issue(violations, UNBOUND), (
        "an issue with no binding passed by default — the 638-of-808 status quo "
        "would be invisible to this validator"
    )


def test_every_violation_carries_the_bound_rule_id_and_an_issue_location(plan_root) -> None:
    """Actionable without re-deriving which issue produced it."""
    violations = _scanner()(_issues(), plan_root=plan_root)
    assert violations, "the scanner reported nothing at all for four broken shapes"
    for v in violations:
        assert getattr(v, "rule_id", None) == _RULE_ID, (
            f"violation carries rule_id {getattr(v, 'rule_id', None)!r}, expected {_RULE_ID!r}"
        )
        assert getattr(v, "location", None), "violation carries no location naming its issue"


def test_the_rule_is_registered_in_the_convention_substrate() -> None:
    """`bind_rule` must resolve the rule, or the validator cannot ship."""
    from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

    try:
        rule = bind_rule(_RULE_ID)
    except RuleNotInRegistryError as exc:
        pytest.fail(
            f"rule {_RULE_ID!r} is not registered in any convention: {exc} "
            "Declare it in its single-node home under "
            "src/atdd/coach/conventions/nodes/."
        )
    assert rule.rule_id == _RULE_ID
