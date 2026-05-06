# URN: component:govern-lifecycle:enforcement-substrate:test_acceptance_phase:backend:tests
# Runtime: python
# Purpose: Substrate enforcement (#410) — every acceptance must declare identity.phase explicitly.

"""Substrate Class 1 conformance: explicit phase declaration (spec v12 §7.3).

Phase is canonical for coach Tier-1 dispatch (§8.1). It cannot be
inferred from harness type or source kind. This validator walks
``<repo>/plan/`` raw and emits a ``Violation`` for every acceptance
missing or carrying an invalid ``identity.phase``.

Failures route through ``assert_disposition_satisfied`` under
``tester.acceptance-violation.acceptance-must-declare-phase`` (strict).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_phase,
    acceptance_urn,
    iter_repo_acceptances,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule("tester.acceptance-violation.acceptance-must-declare-phase")
_VALIDATOR_ID = (
    "test_acceptance_phase::test_every_acceptance_declares_phase"
)
_VALID_PHASES = {"RED", "GREEN", "SMOKE", "REFACTOR"}


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ and return phase-declaration violations."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    violations: List[Violation] = []

    for raw in iter_repo_acceptances(root):
        phase = acceptance_phase(raw.body)
        urn = acceptance_urn(raw.body) or "<no-urn>"

        if phase is None:
            detail = (
                f"acceptance {urn!r} omits identity.phase (required: one of "
                f"RED|GREEN|SMOKE|REFACTOR)"
            )
        elif phase not in _VALID_PHASES:
            detail = (
                f"acceptance {urn!r} declares identity.phase={phase!r} "
                f"which is not one of {sorted(_VALID_PHASES)}"
            )
        else:
            continue

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


def test_every_acceptance_declares_phase() -> None:
    """Every acceptance under plan/ must declare a canonical phase (§7.3)."""
    violations = collect_violations()
    assert_disposition_satisfied(_VALIDATOR_ID, violations)


__all__ = ["collect_violations", "test_every_acceptance_declares_phase"]
