# URN: component:govern-lifecycle:enforcement-substrate:test_security_ref_binding:backend:tests
# Runtime: python
# Purpose: Pytest anchors for the security-mode runner — runtime + validation-time (spec v12 §4.5, §7.4).

"""Pytest anchors for security-rule reference binding (issue #422).

Substrate spec v12 §4.5 anchors the security runner at
``test_security_ref_binding::test_acceptance_ref_resolves_and_passes``;
spec §7.4 anchors the validation-time enforcement rule at
``test_security_ref_binding::test_every_abuse_case_resolves``. Both
functions live in this single module so the bidirectional binding
(rule-id ↔ validator) stays greppable (issue #422 explicit guidance).

  - ``test_acceptance_ref_resolves_and_passes`` — runtime: iterates
    registered security rules, reads the session result map, emits a
    violation per security rule whose bound acceptance failed.
  - ``test_every_abuse_case_resolves`` — validation-time: iterates
    feature.yaml::security.abuse_cases[] for unresolved acceptance_ref
    entries (these were intentionally NOT registered as security rules
    by the walker — the §7.4 two-place split).

The runtime function applies the ``atdd_phase("security")`` pytest mark
so the substrate plugin can reorder it after acceptance items per spec
§4.5 ("acceptance runners executed first, every bound acceptance's
outcome is recorded before the security runner reads").
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import (
    UnresolvedSecurityRef,
    bind_rule,
    find_unresolved_security_refs,
)
from atdd.coach.utils.rule_id_registry import RuleMetadata, build_registry
from atdd.coach.validators._violation import Violation
from atdd.runners.security_runner import run_security_runner


_ENFORCEMENT_RULE_ID = (
    "tester.acceptance-violation.security-rule-must-have-acceptance-ref-resolved"
)
"""Substrate enforcement rule_id for the validation-time check (spec §7.3)."""

_VALIDATION_VALIDATOR_ID = (
    "test_security_ref_binding::test_every_abuse_case_resolves"
)
"""Validator_id for the validation-time enforcement rule (spec §7.3)."""


@pytest.mark.atdd_phase("security")
def test_acceptance_ref_resolves_and_passes() -> None:
    """Runtime: every security rule's bound acceptance must pass in this run.

    Spec v12 §4.5 — iterates rules with ``bound_acceptance_urn`` populated,
    reads the session result map, emits a violation for each whose bound
    acceptance failed. Sequenced after acceptance items by the substrate
    pytest plugin's ``pytest_collection_modifyitems`` reordering.
    """
    run_security_runner()


def test_every_abuse_case_resolves() -> None:
    """Validation-time: every abuse_case must have a resolved acceptance_ref.

    Spec v12 §7.4 — fires for each ``security:`` URN whose
    ``acceptance_ref`` does NOT resolve via SecurityResolver +
    AcceptanceResolver. Does NOT read session state — it walks
    feature.yaml directly. The walker excludes such abuse_cases from the
    registry (so the runtime runner cannot fire on them); this validator
    surfaces them at ``atdd repo validate`` time before any pytest run.
    """
    repo_root = find_repo_root()
    unresolved = find_unresolved_security_refs(repo_root)
    if not unresolved:
        return

    # Look up the enforcement rule's severity from the conformance
    # convention. Defensive fallback to severity 4 mirrors spec §7.3
    # severity declaration so missing-registry entries still produce a
    # well-formed Violation.
    severity = 4
    try:
        enforcement_meta = bind_rule(_ENFORCEMENT_RULE_ID)
        if isinstance(enforcement_meta.severity, int) and 1 <= enforcement_meta.severity <= 5:
            severity = enforcement_meta.severity
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Registry build hiccup — proceed with the default severity rather
        # than mask the underlying conformance failure.
        pass

    violations: List[Violation] = [
        _format_unresolved_violation(ref, severity) for ref in unresolved
    ]
    assert_disposition_satisfied(
        validator_id=_VALIDATION_VALIDATOR_ID,
        violations=violations,
        registry=build_registry(repo_root=repo_root),
        repo_root=repo_root,
    )


def _format_unresolved_violation(
    ref: UnresolvedSecurityRef,
    severity: int,
) -> Violation:
    """Compose a ``Violation`` per spec §6 erratum-corrected sample.

    Issue #422 calls out that spec §6's failure-output example for
    security rules mislabels the validation-time vs runtime modes. This
    formatter is the (a) variant: detail names the unresolvable
    acceptance_ref. The runtime variant (b) lives in security_runner.py
    where it names the bound acceptance whose rule failed in this run.
    """
    acc_ref = ref.acceptance_ref or "<missing>"
    return Violation(
        rule_id=_ENFORCEMENT_RULE_ID,
        severity=severity,
        location=ref.feature_urn or str(ref.feature_path),
        detail=(
            f"abuse_case {ref.abuse_id!r} on {ref.security_urn} "
            f"declares acceptance_ref={acc_ref!r} which does not resolve "
            f"to an authored acceptance in plan/"
        ),
    )
