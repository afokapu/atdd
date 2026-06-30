# URN: component:atdd-plan-core:naming:FeatureNameIsVerbObject:backend:tests
# Acceptance: acc:define-plans:C004-SMOKE-001-feature-verb-object-blocks-at-confirm
# WMBT: wmbt:define-plans:C004
# Phase: SMOKE
# Runtime: python
# Purpose: Foundational feature naming (verb-object) is validator-backed and blocks at Confirm (#1276).
"""Validators for ``planner.feature.name-is-verb-object`` (#1276).

The feature counterpart of the wagon naming rule. The feature segment of a
``feature:<wagon>:<name>`` URN must be verb-object; only that 3rd segment is
checked here (the wagon segment is a reference, governed by the wagon rule).
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.naming import is_verb_object
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)

# GOOD incl. the common action verbs rounded out by the lexicon extension (#1283)
# — route/preview/respond were legitimately-named but falsely rejected at confirm.
GOOD = [
    "make-choice", "track-stock", "authenticate-user", "configure-match",
    "route-request", "preview-changes", "respond-event",
]
BAD = ["respond-and-preview", "route-to-mode", "mode-select", "blitz"]


def test_rule_is_bound() -> None:
    rule = bind_rule("planner.feature.name-is-verb-object")
    assert rule.rule_id == "planner.feature.name-is-verb-object"


@pytest.mark.parametrize("slug", GOOD)
def test_good_feature_names_pass(slug: str) -> None:
    ok, reason = is_verb_object(slug, artifact="feature")
    assert ok, f"{slug!r} should be verb-object but failed: {reason}"


@pytest.mark.parametrize("slug", BAD)
def test_bad_feature_names_fail(slug: str) -> None:
    ok, reason = is_verb_object(slug, artifact="feature")
    assert not ok, f"{slug!r} should violate verb-object but passed"
    assert reason


def _confirm_session_with_feature(feature_urn: str) -> PlanSession:
    s = PlanSession(session_id="f1")
    s.step = Step.CONFIRM.value
    s.issue_ref = "demo-slug"
    s.add_unit(Unit(kind="feature", ref=feature_urn,
                    verdict=Verdict.KEEP.value, spec={"urn": feature_urn}))
    return s


def test_confirm_blocks_non_verb_object_feature(tmp_path) -> None:
    s = _confirm_session_with_feature("feature:manage-users:respond-and-preview")
    with pytest.raises(SessionGateError):
        s.confirm(root=tmp_path)
    assert s.locked is False


def test_confirm_locks_verb_object_feature(tmp_path) -> None:
    s = _confirm_session_with_feature("feature:manage-users:make-choice")
    s.confirm(root=tmp_path)
    assert s.locked is True
