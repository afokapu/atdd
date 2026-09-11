# URN: component:define-plans:artifact-naming:verb_object_corpus_drift:backend:domain
# Purpose: Enforce planner.artifact-naming.verb-object-corpus-drift (#1943) — report
#          the wagon and feature names already on disk that are not verb-object, so
#          naming drift is visible and its size is known.
"""planner.artifact-naming.verb-object-corpus-drift validator (#1943).

The corpus half of verb-object enforcement. The two `name-is-verb-object` rules
gate the AUTHORING path and never look at what is already on disk; this reports
what is.

ADVISORY, and the disposition is load-bearing rather than timid. 101 of 229
authored artifacts do not conform, and the remedy is unaffordable: a name is
carried by the directory, the wagon URN, every feature/WMBT/acceptance URN
beneath it, the test filenames, component URNs in code headers, both registries
and the State Store bindings — renaming one wagon touches roughly 54 files, 37
of them tests. A blocking rule with no affordable remedy is a rule that gets
ignored, so this one reports and lets the debt be paid opportunistically.

The count is the artefact. A RISING count means drift entered outside the
authoring gate, which is the only thing here that is actually actionable.

Rule: planner.artifact-naming.verb-object-corpus-drift
Run:  atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.validators.verb_object_corpus import CAUSE_CONNECTIVE, scan_corpus

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.artifact-naming.verb-object-corpus-drift")
_VALIDATOR_ID = "verb_object_corpus_drift"


def _scan_live() -> List[Violation]:
    plan_root = Path(find_repo_root(Path(__file__))) / "plan"
    violations: List[Violation] = []
    for drift in scan_corpus(plan_root):
        # The remedy differs by cause, so it is stated per finding rather than
        # left to a generic fix_hint that would be wrong half the time.
        remedy = (
            "an `and` connective usually means the artifact does two jobs — split it, "
            "or rename to the single job it actually does"
            if drift.cause == CAUSE_CONNECTIVE else
            "rename to verb-object, or declare the slug in the node's brand_exceptions term"
        )
        violations.append(Violation(
            rule_id=_RULE.rule_id,
            severity=_RULE.severity,
            location=f"plan/:{drift.artifact_kind}:{drift.slug}",
            detail=f"{drift.artifact_kind} '{drift.slug}' is not verb-object "
                   f"[{drift.cause}] — {drift.reason}. {remedy}",
        ))
    return violations


def test_corpus_verb_object_drift_is_reported():
    """planner.artifact-naming.verb-object-corpus-drift — advisory; reports, never blocks."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())
