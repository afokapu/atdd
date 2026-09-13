# Phase: GREEN
# Layer: integration
# Runtime: python
# Purpose: Enforce planner.convention.remedy-must-be-followable (#1965) — a
#          convention node's operative prose must name no absent file and no
#          retired CLI verb, so a remedy read while blocked can be followed.
"""planner.convention.remedy-must-be-followable validator (#1965).

A ``fix_hint`` is the one part of a rule an operator reads *while blocked*. Five
were unfollowable across four nodes — three named a file that is not there, two
instructed ``atdd issue``, removed in #1303 — and a sixth surfaced while the
rule was being designed. Nothing read a ``fix_hint``, so when the verb was
removed and the smoke-acceptance validator renamed, every hint quoting them
stayed exactly as written.

STRICT, and the disposition carries the argument. A naive scan of the 316 nodes
finds 179 of 332 concrete paths absent — 30x the real count — and a rule shipped
against that would have needed 173 exceptions. Decomposed by cause, 137 are
``source.legacy_path`` provenance and 34 are illustrative, leaving 22 operative
and six real. #1958 and #1943 both found a defect whose remedy was unaffordable
(369 of 473, and 101 of 229) and had to settle for ``advisory`` — a rule that
logs a defect rather than refusing it. Six is affordable, so this one gates.

``platform``-gated: in a consumer repo the nodes arrive from the installed
package while the paths they quote are paths in the TOOLKIT repo, so an ungated
rule would flag nearly every path absent in somebody else's repo, for defects
they neither caused nor can fix (#272/#276).

Intentionally unanchored (no ``# Acceptance:`` URN header): this is a repair with
no planned WMBT of its own, so a bidirectional acceptance binding would be
artificial. Mirrors ``test_wmbt_smoke_acceptance_rule_registered.py`` and
``test_hierarchy_coverage.py``.

Rule: planner.convention.remedy-must-be-followable
Run:  pytest src/atdd/planner/validators/test_convention_remedies_are_followable.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.validators.remedy_followability import KIND_RETIRED_VERB, scan_nodes

pytestmark = [pytest.mark.planner, pytest.mark.platform]

_RULE = bind_rule("planner.convention.remedy-must-be-followable")
_VALIDATOR_ID = "convention_remedies_are_followable"


def _scan_live() -> List[Violation]:
    root = Path(find_repo_root(Path(__file__)))
    violations: List[Violation] = []
    for finding in scan_nodes(root):
        # The remedy differs by kind, so it is stated per finding rather than
        # left to a generic hint that would be wrong for one of the two.
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{finding.node_id} ({finding.keypath})",
                detail=(
                    f"{'retired verb' if finding.kind == KIND_RETIRED_VERB else 'absent path'} "
                    f"{finding.token!r} — {finding.detail}"
                ),
            )
        )
    return violations


def test_every_convention_remedy_is_followable() -> None:
    """planner.convention.remedy-must-be-followable — strict; held at zero."""
    if not is_atdd_source_repo():
        pytest.skip(
            "toolkit-self rule: convention prose names paths in the ATDD repo, "
            "which do not exist in a consumer checkout (#272/#276)"
        )
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())
