# URN: component:govern-lifecycle:enforcement-substrate:security_runner:backend:domain
# Runtime: python
# Purpose: Reference-binding runner for security rules — propagates bound-acceptance failure into per-security-rule violations (spec v12 §4.5, §7.4).

"""Security-mode runner (issue #422, substrate spec v12 §4.5 + §7.4).

For every ``RuleMetadata`` carrying a populated ``bound_acceptance_urn``
(security-derived rules whose acceptance_ref resolved at registry-build
time), the runner:

1. Derives the bound rule's id from the bound acceptance URN via
   ``derive_repo_rule_id``.
2. Reads the **session result map** (``session._atdd["rule_outcomes"]``)
   for the bound rule's outcome — populated by the disposition gate +
   substrate pytest plugin during the same run.
3. On ``"failed"``, constructs a ``Violation`` whose detail names the
   bound acceptance URN, and emits it through ``assert_disposition_satisfied``
   with ``validator_id="test_security_ref_binding::test_acceptance_ref_resolves_and_passes"``.

Two failure modes are HANDLED ELSEWHERE:

- ``bound_acceptance_urn`` did NOT resolve at registry-build time → the
  walker DID NOT register the rule (spec v12 §7.4 two-place split). The
  validation-time enforcement rule
  ``tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved``
  surfaces it via ``test_every_abuse_case_resolves`` (peer module).
- ``bound_acceptance_urn`` resolved but the bound rule was not exercised
  in this run (e.g. ``-k`` filter excluded its tests) → the bound rule
  has NO entry in ``rule_outcomes``. The runner SKIPS such rules — a
  security failure cannot be asserted on a contract that wasn't run.
  Coach phase dispatch (§8.1) chooses which rules to run; partial runs
  produce partial outcomes.

The runner is anchored at ``test_security_ref_binding::test_acceptance_ref_resolves_and_passes``
(see the peer test module). All violations across all rules are routed
through a SINGLE ``assert_disposition_satisfied`` call; the gate groups
by ``rule_id`` and emits one failure block per failing rule (spec §4.5).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from atdd.coach.utils.disposition_gate import (
    assert_disposition_satisfied,
    get_active_pytest_session,
    record_rule_outcome,
)
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import (
    RepoYamlValidationError,
    derive_repo_rule_id,
)
from atdd.coach.utils.rule_id_registry import RuleMetadata, build_registry
from atdd.coach.validators._violation import Violation


_logger = logging.getLogger(__name__)


VALIDATOR_ID = "test_security_ref_binding::test_acceptance_ref_resolves_and_passes"
"""Stable validator_id for every security-runner gate call (spec §4.5)."""


def _read_outcomes_from_session(session: Optional[Any]) -> Dict[str, str]:
    """Return the session result map (substrate spec v12 §4.5).

    Returns an empty dict when:
      - No active pytest session (runner invoked outside pytest).
      - Session lacks the ``_atdd`` namespace (pytest plugin not active).
      - ``rule_outcomes`` is missing or wrong-typed (defensive default).
    """
    if session is None:
        return {}
    namespace = getattr(session, "_atdd", None)
    if not isinstance(namespace, dict):
        return {}
    outcomes = namespace.get("rule_outcomes")
    if not isinstance(outcomes, dict):
        return {}
    return outcomes


def _select_security_rules(
    registry: Dict[str, RuleMetadata],
) -> List[RuleMetadata]:
    """Return rules with populated ``bound_acceptance_urn`` (security-derived).

    Filters to security-derived rules registered by the walker (issue
    #422). Rules with broken acceptance_refs are NOT in the registry —
    they fire the §7.4 validation-time enforcement rule instead.
    """
    out: List[RuleMetadata] = []
    seen: set = set()
    for meta in registry.values():
        if not isinstance(meta, RuleMetadata):
            continue
        if not meta.bound_acceptance_urn:
            continue
        if meta.rule_id in seen:
            continue
        seen.add(meta.rule_id)
        out.append(meta)
    return out


def _format_security_detail(
    bound_acc_urn: str,
    bound_rule_id: str,
    bound_outcome: str,
) -> str:
    """Spec §6 sample: name the bound acceptance and its failure."""
    return (
        f"bound acceptance {bound_acc_urn} "
        f"(rule_id={bound_rule_id}) {bound_outcome} in this run"
    )


def _build_violation(
    meta: RuleMetadata,
    bound_rule_id: str,
    bound_outcome: str,
) -> Optional[Violation]:
    """Construct a ``Violation`` for a security rule whose bound rule failed."""
    severity = meta.severity
    if not isinstance(severity, int) or isinstance(severity, bool):
        return None
    if not (1 <= severity <= 5):
        return None
    bound_acc = meta.bound_acceptance_urn or "<unknown>"
    return Violation(
        rule_id=meta.rule_id,
        severity=severity,
        location=meta.feature_urn or bound_acc,
        detail=_format_security_detail(bound_acc, bound_rule_id, bound_outcome),
    )


def collect_security_violations(
    registry: Dict[str, RuleMetadata],
    outcomes: Dict[str, str],
) -> List[Violation]:
    """Pure function: walk security rules and collect failing-bound violations.

    Separated from the gate-emission step so unit tests can inspect the
    list directly without needing pytest.fail interception.
    """
    violations: List[Violation] = []
    for meta in _select_security_rules(registry):
        bound_acc = meta.bound_acceptance_urn or ""
        try:
            bound_rule_id = derive_repo_rule_id(bound_acc)
        except RepoYamlValidationError:
            # Walker accepted the URN but derivation failed here — skip
            # defensively; the §7.4 validator surfaces upstream defects.
            continue

        bound_outcome = outcomes.get(bound_rule_id)
        if bound_outcome is None:
            # Bound rule was not exercised in this run (filtered out, no
            # tests collected, or runner ordering glitch). Skip — we
            # cannot assert a security failure on a contract that wasn't
            # run.
            continue
        if bound_outcome == "failed":
            v = _build_violation(meta, bound_rule_id, bound_outcome)
            if v is not None:
                violations.append(v)
            record_rule_outcome(meta.rule_id, "failed")
        else:
            # Bound contract passed → security rule passes by reference.
            record_rule_outcome(meta.rule_id, "passed")
    return violations


def run_security_runner(
    *,
    registry: Optional[Dict[str, RuleMetadata]] = None,
    repo_root: Optional[Path] = None,
    session: Optional[Any] = None,
) -> None:
    """Run the security runner and route every failure through the gate.

    Single ``assert_disposition_satisfied`` call: the gate groups by
    ``rule_id`` internally and emits one failure block per failing rule
    (per spec §4.5). All failures surface as ONE pytest failure, with
    one block per rule.
    """
    reg = registry if registry is not None else build_registry()
    root = repo_root if repo_root is not None else find_repo_root()
    sess = session if session is not None else get_active_pytest_session()

    outcomes = _read_outcomes_from_session(sess)
    violations = collect_security_violations(reg, outcomes)
    assert_disposition_satisfied(
        validator_id=VALIDATOR_ID,
        violations=violations,
        registry=reg,
        repo_root=root,
    )


__all__ = [
    "VALIDATOR_ID",
    "collect_security_violations",
    "run_security_runner",
]
