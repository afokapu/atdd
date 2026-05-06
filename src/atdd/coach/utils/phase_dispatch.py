# URN: component:govern-lifecycle:enforcement-substrate:phase_dispatch:backend:domain
# Runtime: python
# Purpose: Coach phase-driven dispatch — select repo rules by RuleMetadata.phase per spec v12 §8.1.

"""Coach phase-driven validator dispatch (substrate spec v12 §8.1).

See ``src/atdd/coach/specs/phase-dispatch.spec.md`` for the full
contract. In short: at coach phase ``X``, select every repo rule whose
``RuleMetadata.phase == X``; at ``RED`` additionally include
``phase: GREEN`` rules ("RED expects red"); at ``REFACTOR`` additionally
sweep every strict-disposition rule from the unified registry.

Security rules (registered via #422) carry a populated
``bound_acceptance_urn``. The selector reads the **bound** rule's phase
for dispatch — per §8.1 line 584. Pre-#422 this branch is a no-op.
"""

from __future__ import annotations

import logging
from typing import Iterable, Iterator, List, Optional

from atdd.coach.utils.rule_binding import (
    RuleMetadata,
    RuleNotInRegistryError,
    bind_rule,
    iter_rules,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class PhaseDispatchError(ValueError):
    """Raised for unknown coach phases or invalid dispatch arguments."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_PHASES = ("RED", "GREEN", "SMOKE", "REFACTOR")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_phase(phase: str) -> str:
    if not isinstance(phase, str) or not phase.strip():
        raise PhaseDispatchError(
            f"coach_phase must be a non-empty string, got {phase!r}"
        )
    canonical = phase.strip().upper()
    if canonical not in VALID_PHASES:
        raise PhaseDispatchError(
            f"unknown coach_phase {phase!r}; expected one of {VALID_PHASES}"
        )
    return canonical


def _phase_for_dispatch(rule: RuleMetadata) -> Optional[str]:
    """Resolve the rule's effective phase for dispatch per §8.1 line 584.

    Security rules carry a ``bound_acceptance_urn`` pointing at the
    acceptance whose phase governs activation. Reads that rule's phase
    from the registry; falls back to the rule's own ``phase`` when no
    binding is set.

    Returns ``None`` when the bound rule cannot be resolved — the
    substrate enforcement rule
    ``security-rule-must-have-acceptance-ref-resolved`` (§7.3) surfaces
    this at PLANNED phase, so the selector skips silently here rather
    than failing the whole dispatch.
    """
    bound = rule.bound_acceptance_urn
    if not bound:
        return rule.phase
    try:
        bound_meta = bind_rule(bound)
    except RuleNotInRegistryError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Per spec §7.3 the substrate enforcement rule
        # ``security-rule-must-have-acceptance-ref-resolved`` surfaces an
        # unresolvable ``bound_acceptance_urn`` at PLANNED phase. The
        # dispatch selector skips the rule silently at runtime so a stale
        # binding does not poison phase selection. Log at debug so
        # operators can correlate skipped rules with the upstream
        # validator output.
        _logger.debug(
            "phase_dispatch: bound_acceptance_urn %r on rule %r not in registry — skipping: %s",
            bound, rule.rule_id, exc,
            extra={
                "rule_id": rule.rule_id,
                "bound_acceptance_urn": bound,
                "error_type": type(exc).__name__,
            },
        )
        return None
    return bound_meta.phase


def _is_repo_rule(rule: RuleMetadata) -> bool:
    """Identify repo-derived rules — they discriminate by archetype prefix.

    Repo-walker rule-ids start with ``repo.`` (spec v12 §3.3). Toolkit
    rules use ``coder.`` / ``coach.`` / ``tester.`` / ``planner.``. The
    selector returns toolkit rules only when REFACTOR sweeps strict; at
    other phases it filters to repo rules.
    """
    return isinstance(rule.rule_id, str) and rule.rule_id.startswith("repo.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def select_validator_set(
    coach_phase: str,
    registry: Optional[Iterable[RuleMetadata]] = None,
) -> List[RuleMetadata]:
    """Return the repo-rule subset active at *coach_phase* per §8.1.

    Args:
        coach_phase: One of ``RED``, ``GREEN``, ``SMOKE``, ``REFACTOR``
            (case-insensitive).
        registry: Optional iterable of ``RuleMetadata`` to select from.
            When ``None``, the unified registry exposed by
            ``iter_rules()`` is consumed.

    Returns:
        Deterministic list of selected rules, ordered by ``rule_id``.

    Raises:
        PhaseDispatchError: when ``coach_phase`` is unknown.

    Selection formula (spec v12 §8.1):

        S(X) = { repo rules where phase_for_dispatch(rule) == X }
             ∪ { repo rules where phase_for_dispatch(rule) == "GREEN" if X == RED }
             ∪ { every strict-disposition rule (toolkit or repo) if X == REFACTOR }
    """
    phase = _normalize_phase(coach_phase)
    rules = list(registry) if registry is not None else list(iter_rules())

    selected: List[RuleMetadata] = []
    seen: set = set()

    def _add(rule: RuleMetadata) -> None:
        if rule.rule_id in seen:
            return
        seen.add(rule.rule_id)
        selected.append(rule)

    # Set 1: repo rules whose effective phase matches the coach phase.
    # Set 2: at RED only, additionally include phase=GREEN repo rules
    #        ("RED expects red" — §8.1 paragraph 5).
    accepted_phases = {phase}
    if phase == "RED":
        accepted_phases.add("GREEN")

    for rule in rules:
        if not _is_repo_rule(rule):
            continue
        effective = _phase_for_dispatch(rule)
        if effective is None:
            continue
        if effective.upper() in accepted_phases:
            _add(rule)

    # Set 3: REFACTOR sweep — every strict-disposition rule (toolkit OR
    # repo) regardless of phase (§8.1 paragraph 4).
    if phase == "REFACTOR":
        for rule in rules:
            if rule.disposition == "strict":
                _add(rule)

    selected.sort(key=lambda r: r.rule_id)
    return selected


def classify_violation(
    coach_phase: str,
    rule: RuleMetadata,
    violation_emitted: bool,
) -> str:
    """Classify a violation outcome per coach v6 §4.1 + spec v12 §8.1 ¶5.

    Returns one of:
      - ``"expected"`` — violation at RED for a phase=GREEN rule (RED expects red).
      - ``"regression"`` — phase=GREEN rule passes at RED (the contract is
        already passing — coach surfaces this so the agent doesn't skip
        the GREEN write).
      - ``"failure"`` — violation at GREEN/SMOKE for a phase=X-matching rule.
      - ``"pass"`` — no violation; rule is satisfied for this phase.
    """
    phase = _normalize_phase(coach_phase)
    rule_phase = _phase_for_dispatch(rule)
    rule_phase_upper = rule_phase.upper() if isinstance(rule_phase, str) else None

    if phase == "RED" and rule_phase_upper == "GREEN":
        return "expected" if violation_emitted else "regression"

    return "failure" if violation_emitted else "pass"


def iter_selected(
    coach_phase: str,
    registry: Optional[Iterable[RuleMetadata]] = None,
) -> Iterator[RuleMetadata]:
    """Streaming variant of ``select_validator_set``."""
    yield from select_validator_set(coach_phase, registry=registry)


__all__ = [
    "PhaseDispatchError",
    "VALID_PHASES",
    "classify_violation",
    "iter_selected",
    "select_validator_set",
]
