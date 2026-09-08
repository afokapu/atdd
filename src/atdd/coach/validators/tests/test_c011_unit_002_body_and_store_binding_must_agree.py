# URN: test:govern-lifecycle:bind-issue-feature:C011-UNIT-002-body-and-store-binding-must-agree
# Acceptance: acc:govern-lifecycle:C011-UNIT-002-body-and-store-binding-must-agree
# WMBT: wmbt:govern-lifecycle:C011
# Phase: RED
# Layer: domain
# Runtime: python
# Assertion: behavioral
# Purpose: The body's Feature row and the stored work_item.data.feature are held to each other, so the #1626 divergence is a reported violation rather than an invisible state.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:C011-UNIT-002-body-and-store-binding-must-agree
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:C011

Purpose: two places record a feature; nothing compares them.

Measured 2026-07-28 on #1626: body populated, store NULL. Reproduced on #1635
itself — its body now declares feature:govern-lifecycle:bind-issue-feature
while its store still reads feature:govern-lifecycle:reliable-manifest-
registration, and no surface reports the disagreement.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    control_root,
    optional_attr,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_SCANNER_MODULE = "atdd.coach.validators.issue_feature_binding_scanner"
_SCANNER_ATTR = "scan_feature_bindings"
_RULE_ID = "coach.issue.feature-binding-must-resolve"

OTHER_FEATURE_URN = "feature:govern-lifecycle:reliable-manifest-registration"

AGREE = 95001
BODY_ONLY = 95002   # the #1626 shape: body set, store NULL
STORE_ONLY = 95003
DISAGREE = 95004    # the #1635 shape: both set, to different features


def _scanner():
    fn = optional_attr(_SCANNER_MODULE, _SCANNER_ATTR)
    assert fn is not None, (
        f"no feature-binding scanner: expected {_SCANNER_MODULE}.{_SCANNER_ATTR}"
    )
    return fn


@pytest.fixture()
def plan_root(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root, wmbts=("wmbt:govern-lifecycle:Y006",))
    # A second resolvable feature so "disagree" is not merely "one is absent".
    import yaml
    other = root / "plan" / "govern_lifecycle" / "features" / "reliable_manifest_registration.yaml"
    other.write_text(yaml.safe_dump({
        "urn": OTHER_FEATURE_URN,
        "wagon": "wagon:govern-lifecycle",
        "description": "An unrelated feature that nonetheless resolves.",
        "sizing": {"wmbts": 0, "footprint_score": 1, "footprint_size": "XS"},
        "wmbts": [],
        "components": {"backend": {"application": [
            {"type": "use_cases", "count": 1, "rationale": "unrelated but resolvable"},
        ]}},
    }, sort_keys=False), encoding="utf-8")
    return root


def _issues():
    return [
        {"number": AGREE, "feature": FEATURE_URN,
         "body": f"| Feature | `{FEATURE_URN}` |"},
        {"number": BODY_ONLY, "feature": None,
         "body": f"| Feature | `{FEATURE_URN}` |"},
        {"number": STORE_ONLY, "feature": FEATURE_URN,
         "body": "no Feature row at all"},
        {"number": DISAGREE, "feature": OTHER_FEATURE_URN,
         "body": f"| Feature | `{FEATURE_URN}` |"},
    ]


def _for_issue(violations, number):
    return [v for v in violations if str(number) in str(getattr(v, "location", ""))]


def test_agreement_produces_no_violation(plan_root) -> None:
    assert _for_issue(_scanner()(_issues(), plan_root=plan_root), AGREE) == []


def test_body_set_with_a_null_stored_feature_is_reported(plan_root) -> None:
    """The #1626 shape measured on 2026-07-28."""
    assert _for_issue(_scanner()(_issues(), plan_root=plan_root), BODY_ONLY), (
        "body declared a feature the store never received, and nothing reported it"
    )


def test_store_set_with_the_body_row_absent_is_reported(plan_root) -> None:
    assert _for_issue(_scanner()(_issues(), plan_root=plan_root), STORE_ONLY), (
        "the store carries a binding the body does not declare, unreported"
    )


def test_two_different_feature_urns_are_reported_quoting_both(plan_root) -> None:
    """The #1635 shape — a reader must be able to tell which side to correct."""
    reported = _for_issue(_scanner()(_issues(), plan_root=plan_root), DISAGREE)
    assert reported, "body and store named different features and nothing reported it"
    details = " ".join(str(getattr(v, "detail", "")) for v in reported)
    assert FEATURE_URN in details and OTHER_FEATURE_URN in details, (
        "the violation does not quote both values, so it cannot say which side to fix"
    )


def test_the_scanner_binds_its_rule_at_module_import() -> None:
    """`bind_rule` at import time is the bidirectional binding contract."""
    import importlib

    try:
        module = importlib.import_module(_SCANNER_MODULE)
    except ImportError:
        pytest.fail(f"{_SCANNER_MODULE} does not exist yet")

    bound = getattr(module, "_RULE", None)
    assert bound is not None and getattr(bound, "rule_id", None) == _RULE_ID, (
        f"{_SCANNER_MODULE} must call bind_rule({_RULE_ID!r}) at module import "
        "(SPEC-COACH-RULEID-0007)"
    )
