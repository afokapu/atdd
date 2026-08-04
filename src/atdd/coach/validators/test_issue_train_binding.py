# URN: component:govern-lifecycle:bind-issue-train:TrainBindingValidator:backend:tests
# Purpose: Enforce coach.train-reference.resolves-to-registered-train and
#          coach.train-reference.resolved-train-has-interlocking (#1590) — an
#          issue's declared train must resolve against the repository's OWN
#          registry, and the train it resolves to should carry an interlocking.
"""coach.train-reference.* validators (#1590).

Scans the local State Store: every non-terminal issue-backed work item that
DECLARES a train must resolve it against the registry of the repository under
scan, and the train it resolves to should be routed through by an interlocking
that repository declares.

Two rules, two test functions, two dispositions — deliberately not one. The
disposition gate reads disposition per rule_id, so folding both assertions into
one function would force one policy onto two failure modes whose measured
populations differ by two orders of magnitude (16 unresolvable references vs 148
unrouted trains, 2026-08-03 on ff55607b). Each function therefore reports only
its own rule's violations.

Deliberately carries NO marker. ``atdd validate coach --local --skip-api``
selects ``-m "(not github_api) and (not platform)"``, so a ``platform``-marked
validator is silently deselected by the very gate that is supposed to run it.
This validator reads the store and ``plan/`` off disk and makes no provider
call, so it needs neither marker and the gate cannot skip it.

Both rules are ``advisory`` with a baseline recorded in their nodes' ``terms``.
That is the ADOPTION path for a new rule over a pre-existing corpus, not a
relaxation: the WRITE side is strict (every sanctioned setter refuses an
unresolvable train), so the baseline can only shrink. Escalate each node's
disposition when its set reaches zero.

Rules: coach.train-reference.resolves-to-registered-train
       coach.train-reference.resolved-train-has-interlocking
Run:   atdd validate coach
"""
from __future__ import annotations

from typing import List

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.validators.issue_train_binding_scanner import (
    _INTERLOCKING_RULE, _RULE, scan_store_train_references, scan_train_references,
)

_VALIDATOR_ID = "test_issue_train_binding"
_RULE_ID = "coach.train-reference.resolves-to-registered-train"
_INTERLOCKING_RULE_ID = "coach.train-reference.resolved-train-has-interlocking"


def _scan_live() -> List[Violation]:
    try:
        return scan_store_train_references(find_repo_root())
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        # An unreachable store must not break the gate; the store-health
        # validators own that failure mode.
        return []


def _only(rule_id: str, violations: List[Violation]) -> List[Violation]:
    """The subset belonging to one rule, so each gate call sees one disposition."""
    return [v for v in violations if v.rule_id == rule_id]


def test_rules_are_bound() -> None:
    """The bidirectional binding contract (SPEC-COACH-RULEID-0007), both rules."""
    assert bind_rule(_RULE_ID).rule_id == _RULE_ID
    assert bind_rule(_INTERLOCKING_RULE_ID).rule_id == _INTERLOCKING_RULE_ID
    assert _RULE.rule_id == _RULE_ID
    assert _INTERLOCKING_RULE.rule_id == _INTERLOCKING_RULE_ID


def test_scanner_reports_an_unregistered_train(tmp_path) -> None:
    """Fault control: the scan must be able to fail, or it enforces nothing.

    Resolved against a plan tree this test BUILDS, never the ambient repo. The
    first version of this control passed ``find_repo_root()`` and was therefore
    green inside atdd and red in a consumer repo, where there is no ``plan/``
    tree, the scan correctly reports nothing, and the control read that correct
    silence as a broken scanner. `validate-consumer` caught it — which is the
    node's own thesis landing on the node's own test: a check that works only
    because it runs inside atdd is the defect, not the evidence.

    An empty ``plan/`` directory is the whole fixture. It makes the registry
    resolvable-but-empty, which is exactly the state in which a well-formed
    reference must be reported as unregistered.
    """
    (tmp_path / "plan").mkdir()

    violations = scan_train_references(
        [{"number": 1, "train": "train:no-such-subject:no-such-train"}],
        plan_root=tmp_path,
    )
    assert violations, "the scanner passed a train reference that resolves to nothing"
    assert violations[0].rule_id == _RULE.rule_id


def test_a_repo_with_no_plan_tree_reports_nothing(tmp_path) -> None:
    """The other half of the same lesson, asserted rather than left implicit.

    A consumer repo with no ``plan/`` tree has no registry to hold references
    against, so silence there is the CORRECT answer and not a hole. Pinning it
    stops the fault control above from being 'fixed' back into ambient
    resolution by someone who reads the silence as a bug.
    """
    assert scan_train_references(
        [{"number": 1, "train": "train:no-such-subject:no-such-train"}],
        plan_root=tmp_path,
    ) == []


def test_train_references_resolve() -> None:
    """Every declared train must resolve against the repository's own registry.

    ``bind_rule`` is called here, not merely at module import, because
    ``coach.rule-id.validator-binding-violation`` resolves the rule's declared
    validator and requires THAT function body to name the rule it enforces — a
    module-level binding read through an import is invisible to it.
    """
    rule = bind_rule("coach.train-reference.resolves-to-registered-train")
    assert rule.rule_id == _RULE_ID
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=_only(_RULE_ID, _scan_live()),
    )


def test_resolved_trains_have_an_interlocking() -> None:
    """A resolved train with no interlocking route is the second-order dangling
    reference: the issue resolves to a train and the train resolves to no route,
    so a gate reading that train's interlocking has no subject.

    Reported against its OWN rule id so its disposition is governed separately
    from the reference rule's — the populations are two orders of magnitude apart.
    """
    rule = bind_rule("coach.train-reference.resolved-train-has-interlocking")
    assert rule.rule_id == _INTERLOCKING_RULE_ID
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=_only(_INTERLOCKING_RULE_ID, _scan_live()),
    )
