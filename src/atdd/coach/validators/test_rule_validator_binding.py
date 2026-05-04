# URN: component:govern-lifecycle:enforcement-substrate:test_rule_validator_binding:backend:domain
# Runtime: python
# Purpose: Reverse-coherence — every enforceable rule names a validator that actually binds it (issue #399).

"""Reverse rule-coherence validator (issue #399 Phase 3 + Phase 5).

Closes the loop opened by ``test_rule_id_registry_coherence.py``:

    * Forward coherence  (already shipping):
        every ``bind_rule("<id>")`` must resolve to a declared rule.
    * Reverse coherence  (this validator):
        every rule with disposition ∈ {strict, suppress-and-clean, advisory}
        MUST name a validator that actually contains a literal
        ``bind_rule("<this rule id>")`` call.

Rules with ``disposition: documentation-only`` MUST NOT carry a
``validator:`` field — they are explicitly unenforced.

Failures emit ``Violation`` records keyed off
``coach.rule-id.validator-binding-violation``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.utils.rule_id_registry import build_registry
from atdd.coach.utils.rule_validator_resolver import (
    ResolvedValidator,
    ValidatorResolutionError,
    resolve_validator,
)
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach]


_RULE = bind_rule("coach.rule-id.validator-binding-violation")


_NAMESPACED_RE = re.compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)


_ENFORCED_DISPOSITIONS = {"strict", "suppress-and-clean", "advisory"}


def _archetype_of(rule_id: str) -> str:
    """Extract the leading archetype segment from a namespaced id."""
    return rule_id.split(".", 1)[0]


def _build_violations() -> List[Violation]:
    """Walk the registry and return reverse-coherence violations."""
    registry = build_registry()
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
                violations.append(
                    Violation(
                        rule_id="coach.rule-id.validator-binding-violation",
                        severity=3,
                        location=loc,
                        detail=(
                            f"rule {rule_id!r} is documentation-only but carries "
                            f"validator:{validator_field!r}; remove the validator "
                            f"field or change the disposition."
                        ),
                    )
                )
            continue

        if disposition not in _ENFORCED_DISPOSITIONS:
            # Unmigrated rule (no disposition) — out of scope for reverse
            # coherence; forward coherence + disposition gates handle it.
            continue

        if not validator_field:
            violations.append(
                Violation(
                    rule_id="coach.rule-id.validator-binding-violation",
                    severity=3,
                    location=loc,
                    detail=(
                        f"rule {rule_id!r} has disposition {disposition!r} but "
                        f"declares no validator: field. Either set "
                        f"validator: '<module>::<func>' or change disposition "
                        f"to documentation-only."
                    ),
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
            violations.append(
                Violation(
                    rule_id="coach.rule-id.validator-binding-violation",
                    severity=3,
                    location=loc,
                    detail=(
                        f"rule {rule_id!r} validator {validator_field!r} could "
                        f"not be resolved: {exc}"
                    ),
                )
            )
            continue

        # Function exists. Does it bind THIS rule?
        if rule_id not in resolved.bound_rule_ids and not (
            set(meta.aliases) & resolved.bound_rule_ids
        ):
            violations.append(
                Violation(
                    rule_id="coach.rule-id.validator-binding-violation",
                    severity=3,
                    location=f"{resolved.module_path}",
                    detail=(
                        f"rule {rule_id!r} names validator "
                        f"{validator_field!r}, but the function body never "
                        f"calls bind_rule({rule_id!r}). Found "
                        f"{sorted(resolved.bound_rule_ids)!r}."
                    ),
                )
            )

    return violations


@pytest.mark.coach
def test_every_enforced_rule_has_real_validator():
    """Reverse coherence: enforced rules name a validator that binds them."""
    violations = _build_violations()
    if violations:
        formatted = "\n".join(f"  - {v.location}: {v.detail}" for v in violations)
        pytest.fail(
            "\nReverse rule-coherence found "
            f"{len(violations)} violation(s):\n\n{formatted}\n\n"
            "Either add a `validator:` back-reference + bind_rule call, or "
            "set `disposition: documentation-only`."
        )


__all__ = ["test_every_enforced_rule_has_real_validator"]
