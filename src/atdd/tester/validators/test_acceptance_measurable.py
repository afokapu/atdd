# URN: component:govern-lifecycle:enforcement-substrate:test_acceptance_measurable:backend:tests
# Runtime: python
# Purpose: Substrate enforcement (#410) — every acceptance must declare harness.type OR signal.metric+threshold (or both).

"""Substrate Class 1 conformance: acceptance measurability (spec v12 §7.3).

Walks ``<repo>/plan/`` raw and emits a ``Violation`` for every acceptance
that fails the measurability invariant from §4.3:

  EITHER ``harness.type`` declared
  OR     BOTH ``signal.metric`` AND ``signal.threshold``
  OR     both.

Failures route through ``assert_disposition_satisfied`` under the
disposition the convention attaches to
``tester.acceptance-violation.acceptance-must-be-measurable`` (strict).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_urn,
    assert_substrate_strict,
    has_harness_type,
    has_signal_metric_and_threshold,
    iter_repo_acceptances,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule("tester.acceptance-violation.acceptance-must-be-measurable")
_VALIDATOR_ID = (
    "test_acceptance_measurable::test_every_acceptance_has_enforcement"
)


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ and return measurability violations.

    Pure function: separated from the gate-emission step so tests can
    inspect the list directly without pytest.fail interception.
    """
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    violations: List[Violation] = []

    for raw in iter_repo_acceptances(root):
        if has_harness_type(raw.body) or has_signal_metric_and_threshold(raw.body):
            continue
        urn = acceptance_urn(raw.body) or "<no-urn>"
        detail = (
            f"acceptance {urn!r} is not measurable: declares neither "
            f"harness.type nor signal.metric+signal.threshold (both required "
            f"together)"
        )
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=raw.location,
                detail=detail,
                fix_hint_ref=_RULE.fix_hint_ref,
            )
        )

    return violations


def test_every_acceptance_has_enforcement() -> None:
    """Every acceptance under plan/ must be measurable (§7.3)."""
    violations = collect_violations()
    assert_substrate_strict(_VALIDATOR_ID, violations)


__all__ = ["collect_violations", "test_every_acceptance_has_enforcement"]
