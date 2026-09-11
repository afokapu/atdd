# URN: component:define-plans:criteria:metric_mapping_corpus_drift:backend:tests
# Acceptance: acc:define-plans:E004-SMOKE-001-mapping-rule-bound-and-run
# WMBT: wmbt:define-plans:E004
# Phase: SMOKE
# Runtime: python
# Purpose: Enforce planner.criteria.metric-mapping (#1958) — report every WMBT the
#          dimension->metric mapping covers that states no executable bar, so a
#          convention that names a metric stops describing something nothing checks.
"""planner.criteria.metric-mapping validator (#1958).

The node said each WMBT dimension+direction maps to a default `metric_id` —
`likelihood/minimize` is an error ratio, `likelihood/maximize` a success ratio,
`frequency/decrease` an occurrence rate — and bound nothing. No
`implementation:`, no `validation:`, and `metric_id` appeared in no schema and
no validator. Same shape as #1548: a node that declares a contract and leaves it
unenforced.

Measured over the corpus: 368 of 472 WMBTs carry a dimension+direction the
mapping covers, and NONE of them states an executable bar. The single WMBT that
does (`govern_lifecycle/D010`, `hardcoded_theme_map_literal_count`) is
`quantity/minimize`, which the mapping does not cover. A ratio with no stated
bar is a comment.

ADVISORY, and the disposition is load-bearing rather than timid. All 368 would
fail on day one, and the remedy is not yet affordable: a stated bar resolves
through `runners/metric_runner.py` to a module under `.atdd/metrics/` or
`src/atdd/runners/metrics/`, and neither `error_ratio`, `success_ratio` nor
`occurrence_rate` exists — `src/atdd/runners/metrics/` holds exactly one module.
Requiring a bar today would require authoring the metrics too, which #1958 puts
out of scope. So this reports and lets the debt be paid deliberately, per the
issue's Decision #2: phase it, never fail 368 at once.

The count is the artefact. A RISING count means a rate-shaped WMBT was authored
with no bar after the mapping was bound, which is the only thing here that is
immediately actionable.

Rule: planner.criteria.metric-mapping
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
from atdd.planner.validators.metric_mapping import CAUSE_OFF_MAP, scan_corpus

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.criteria.metric-mapping")
_VALIDATOR_ID = "metric_mapping_corpus_drift"


def _scan_live() -> List[Violation]:
    plan_root = Path(find_repo_root(Path(__file__))) / "plan"
    violations: List[Violation] = []
    for finding in scan_corpus(plan_root):
        # The remedy differs by cause, so it is stated per finding rather than
        # left to a generic fix_hint that would be wrong for one of the two.
        remedy = (
            f"either state {finding.metric_id!r} on the acceptance, or fix the "
            f"mapping if this dimension+direction does not actually mean that metric"
            if finding.cause == CAUSE_OFF_MAP else
            f"state signal.metric {finding.metric_id!r} and a signal.threshold on "
            f"one acceptance, or change the WMBT's dimension+direction if it is not "
            f"a rate"
        )
        violations.append(Violation(
            rule_id=_RULE.rule_id,
            severity=_RULE.severity,
            location=finding.wmbt_urn,
            detail=f"{finding.dimension}/{finding.direction} maps to "
                   f"{finding.metric_id} [{finding.cause}] — {finding.detail}. {remedy}",
        ))
    return violations


def test_mapped_wmbts_without_an_executable_bar_are_reported():
    """planner.criteria.metric-mapping — advisory; reports, never blocks."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())
