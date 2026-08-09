# URN: component:govern-lifecycle:enforcement-substrate:test_rule_validator_binding:backend:domain
# Runtime: python
# Purpose: Reverse-coherence — every enforceable rule names a validator that actually binds it (issue #399).

"""Reverse rule-coherence validator (issue #399 Phase 3 + Phase 5).

Closes the loop opened by ``test_rule_id_registry_coherence.py``:

    * Forward coherence  (already shipping):
        every ``bind_rule("<id>")`` must resolve to a declared rule.
    * Reverse coherence  (this validator):
        every rule with disposition ∈ {strict, suppress-and-clean, advisory}
        MUST name real, bidirectional, executable enforcement.

Rules with ``disposition: documentation-only`` MUST NOT carry a
``validator:`` field — they are explicitly unenforced.

WHAT COUNTS AS PROOF (three things, one requirement — #1773 / program #1772).
The requirement above has never been weakened; what has widened, twice, is the
vocabulary of evidence that satisfies it:

  1. a literal ``bind_rule("<this rule id>")`` call inside the named validator
     (the original, and still the common case);
  2. an executing convention variant — ``resolved.is_convention`` (#1207) —
     whose clean baseline plus fault injection is its live coverage;
  3. a COMPLETE bound provider realization
     (:mod:`atdd.coach.validators._bound_realization`), where the digest-coherent
     binding lock selects one implementation for the rule and that exact
     implementation back-references it, emits it, reports through a resolvable
     channel, is runnable, and is blockingly executed.

All three are admitted by RESOLUTION, not by declaration: none of them lets a
rule assert its own enforcement. Proof 3 exists because the requirement was
agnostic in wording but not in evidence — the only thing it could accept was a
Python callsite in core, so a rule an admitted provider already enforced had to
keep a ceremonial core twin, and the migration to an agnostic core could only
ever add twins.

PLACEMENT IS THE MECHANISM, NOT AN OPTIMISATION. Proof 3 is evaluated BEFORE the
``not validator_field`` branch and before ``resolve_validator``. Both of those
reject a provider-only rule strictly earlier than any point at which a lock could
be consulted, so a discharge placed after them would be unreachable — and a
provider-proven rule would have to carry a placeholder ``validator:`` value to
get far enough to be discharged, which would make the discharge a new
declaration in disguise. Evaluated here, it needs none.

Failures emit ``Violation`` records keyed off
``coach.rule-id.validator-binding-violation``.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.utils.rule_id_registry import build_registry
from atdd.coach.utils.rule_validator_resolver import (
    ResolvedValidator,
    ValidatorResolutionError,
    resolve_validator,
)
from atdd.coach.validators._bound_realization import BoundRealizationResolver
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach]

_logger = logging.getLogger(__name__)


_RULE = bind_rule("coach.rule-id.validator-binding-violation")


_NAMESPACED_RE = re.compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)


_ENFORCED_DISPOSITIONS = {"strict", "suppress-and-clean", "advisory"}


def _archetype_of(rule_id: str) -> str:
    """Extract the leading archetype segment from a namespaced id."""
    return rule_id.split(".", 1)[0]


def _realization_resolver() -> Optional[BoundRealizationResolver]:
    """The bound-realization resolver for the repo under validation, or ``None``.

    Bound to the CONSUMER-local substrate only — :meth:`for_repo` never falls
    back to the toolkit install, so a consumer can never be handed a discharge
    manufactured from the toolkit's own vendored lock.

    ``None`` when the repo root cannot be determined at all. That is strictly
    the pre-#1773 behaviour (no third proof is offered, so every rule needs
    proof 1 or proof 2), which is the safe direction to fail: an unavailable
    resolver withholds discharges, it never grants them.
    """
    root: Optional[Path] = None
    try:
        from atdd.coach.utils.repo import find_repo_root

        root = find_repo_root()
    except Exception as exc:
        _logger.debug(
            "reverse coherence: repo root unresolvable, so only literal and "
            "convention-variant proofs are offered: %s",
            exc,
            extra={"error_type": type(exc).__name__},
        )
        root = None
    if root is None:
        return None
    return BoundRealizationResolver.for_repo(root)


def _build_violations() -> List[Violation]:
    """Walk the registry and return reverse-coherence violations."""
    registry = build_registry()
    realizations = _realization_resolver()
    seen_canonicals = set()
    violations: List[Violation] = []

    # Iterate over canonical rules only — aliases live in the same dict.
    for rule_id, meta in registry.items():
        if rule_id != meta.rule_id:
            continue  # alias key — skip; canonical entry handled separately.
        if rule_id in seen_canonicals:
            continue
        seen_canonicals.add(rule_id)

        if not _NAMESPACED_RE.match(rule_id):
            # Legacy-shaped ids (still allowed via legacy_grammar) opt out of
            # reverse coherence — they can't carry a `validator:` field by
            # construction. Forward coherence already polices their bind_rule
            # callsites.
            continue

        disposition = meta.disposition
        validator_field = meta.validator
        loc = f"{meta.convention_path}"

        if disposition == "documentation-only":
            if validator_field:
                detail = (
                    f"rule {rule_id!r} is documentation-only but carries "
                    f"validator:{validator_field!r}; remove the validator "
                    f"field or change the disposition."
                )
                if meta.description:
                    detail += f" | rule purpose: {meta.description}"
                violations.append(
                    Violation(
                        rule_id=_RULE.rule_id,
                        severity=_RULE.severity,
                        location=loc,
                        detail=detail,
                    )
                )
            continue

        if disposition not in _ENFORCED_DISPOSITIONS:
            # Unmigrated rule (no disposition) — out of scope for reverse
            # coherence; forward coherence + disposition gates handle it.
            continue

        # PROOF 3 (#1773) — a complete bound provider realization, evaluated
        # AHEAD of both rejection branches below. See the module docstring: after
        # them it would be unreachable, and reaching them would require a
        # placeholder `validator:` value that would turn this discharge back into
        # a declaration. Nothing here can be satisfied by a rule asserting its own
        # enforcement: it is resolved from the digest-coherent binding lock and the
        # exact implementation manifest that lock selects.
        #
        # ONLY a PROVEN proof discharges. `NOT_APPLICABLE` (a consumer with no
        # local substrate) means this branch is owed nothing, NOT that the rule is
        # proven — such a rule falls through and must satisfy proof 1 or proof 2
        # like any other. `discharges` is read off the proof rather than
        # recomputed here so the two cannot drift.
        proof = realizations.proof_for(rule_id) if realizations is not None else None
        if proof is not None and proof.discharges:
            continue

        if not validator_field:
            detail = (
                f"rule {rule_id!r} has disposition {disposition!r} but "
                f"declares no validator: field. Either set "
                f"validator: '<module>::<func>' or change disposition "
                f"to documentation-only."
            )
            if proof is not None:
                # Say WHY the provider route did not carry it either. Without
                # this the operator sees only "declare a validator" and cannot
                # tell that a realization exists but is one link short.
                detail += (
                    f" | bound-realization proof: {proof.basis} — {proof.detail}"
                )
            if meta.description:
                detail += f" | rule purpose: {meta.description}"
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=loc,
                    detail=detail,
                )
            )
            continue

        archetype = _archetype_of(rule_id)
        try:
            resolved: ResolvedValidator = resolve_validator(
                archetype=archetype,
                validator_field=validator_field,
            )
        except (ValidatorResolutionError, ValueError) as exc:
            detail = (
                f"rule {rule_id!r} validator {validator_field!r} could "
                f"not be resolved: {exc}"
            )
            if meta.description:
                detail += f" | rule purpose: {meta.description}"
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=loc,
                    detail=detail,
                )
            )
            continue

        # A convention-variant enforcer (conventions/<family>/<stem>::<func>) binds
        # via parity/execution on the composed graph, not a bind_rule literal
        # (#1207). Accept it as a valid binding without the callsite requirement —
        # the variant's clean-baseline + fault-injection are its live coverage.
        if resolved.is_convention:
            continue

        # Function exists. Does it bind THIS rule?
        if rule_id not in resolved.bound_rule_ids and not (
            set(meta.aliases) & resolved.bound_rule_ids
        ):
            detail = (
                f"rule {rule_id!r} names validator "
                f"{validator_field!r}, but the function body never "
                f"calls bind_rule({rule_id!r}). Found "
                f"{sorted(resolved.bound_rule_ids)!r}."
            )
            if meta.description:
                detail += f" | rule purpose: {meta.description}"
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{resolved.module_path}",
                    detail=detail,
                )
            )

    return violations


@pytest.mark.coach
def test_every_enforced_rule_has_real_validator():
    """Reverse coherence: enforced rules name a validator that binds them."""
    violations = _build_violations()
    if not violations:
        return
    formatted = "\n".join(f"  - {v.location}: {v.detail}" for v in violations)
    if os.environ.get("ATDD_ALLOW_ORPHAN_RULES"):
        # Emergency opt-out — emit warning, do NOT fail (issue #399).
        import warnings
        warnings.warn(
            f"[ATDD_ALLOW_ORPHAN_RULES] Reverse rule-coherence found "
            f"{len(violations)} violation(s); gate demoted to WARN:\n\n"
            f"{formatted}",
            UserWarning,
        )
        return
    pytest.fail(
        "\nReverse rule-coherence found "
        f"{len(violations)} violation(s):\n\n{formatted}\n\n"
        "Either add a `validator:` back-reference + bind_rule call, or "
        "set `disposition: documentation-only`. "
        "Emergency opt-out: atdd validate coach --allow-orphan-rules."
    )


__all__ = ["test_every_enforced_rule_has_real_validator"]
