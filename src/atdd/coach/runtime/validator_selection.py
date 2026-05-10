# URN: component:govern-lifecycle:enforcement-substrate:validator_selection:backend:domain
# Runtime: python
# Purpose: Per-phase validator selection per spec §6.5 (toolkit slice) and substrate v12 §8.1 (repo-rule slice).

"""Per-phase validator selection (spec §6.5, substrate v12 §8.1).

Public API:
  - build_validator_set(phase, config, registry) -> ValidatorSet
  - ValidatorSet (immutable)

The selected set is ``toolkit_slice ∪ repo_slice``:

Toolkit slice (§6.5 mapping table):
  - PLANNED: planner.* + tester.acceptance-violation.* (substrate enforcement)
  - RED: tester.* + coach.rule-id-uniqueness
  - GREEN: coder.*
  - SMOKE: tester.* (smoke-filtered downstream)
  - REFACTOR: coder.* with disposition=strict (regression sweep)

Repo-rule slice (substrate v12 §8.1):
  - Every repo.* rule whose RuleMetadata.phase matches the current coach phase.
  - At REFACTOR, additionally sweeps all strict-disposition repo rules
    regardless of phase.

Override:
  - ``config.validators.selection`` can be a dict mapping phase names to
    explicit rule-id lists, overriding the toolkit slice for that phase.
  - Repo-rule slice is never overridden (substrate v12 §2 unsuppressibility).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Union

from atdd.coach.utils.coach_config import CoachConfig
from atdd.coach.utils.rule_binding import RuleMetadata, iter_rules


VALID_PHASES = ("PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR")

# Extra toolkit rule IDs included at specific phases (not archetype-filtered).
_RED_EXTRA_IDS = frozenset({"coach.rule-id-uniqueness"})

# Namespace prefix for substrate enforcement at PLANNED.
_PLANNED_SUBSTRATE_PREFIX = "tester.acceptance-violation."


@dataclass(frozen=True)
class ValidatorSet:
    """Phase-selected validator set: toolkit slice ∪ repo-rule slice."""

    toolkit_slice: Tuple[RuleMetadata, ...]
    repo_slice: Tuple[RuleMetadata, ...]

    @property
    def all_rules(self) -> Tuple[RuleMetadata, ...]:
        return self.toolkit_slice + self.repo_slice


class PhaseSelectionError(ValueError):
    """Raised for unknown coach phases or invalid selection arguments."""


def _normalize_phase(phase: str) -> str:
    if not isinstance(phase, str) or not phase.strip():
        raise PhaseSelectionError(
            f"phase must be a non-empty string, got {phase!r}"
        )
    canonical = phase.strip().upper()
    if canonical not in VALID_PHASES:
        raise PhaseSelectionError(
            f"unknown phase {phase!r}; expected one of {VALID_PHASES}"
        )
    return canonical


def _is_toolkit_rule(rule: RuleMetadata) -> bool:
    return not rule.rule_id.startswith("repo.")


def _toolkit_matches_phase(rule: RuleMetadata, phase: str) -> bool:
    """Return True if *rule* is a toolkit rule that belongs in *phase*'s §6.5 mapping."""
    rid = rule.rule_id
    archetype = rid.split(".", 1)[0]

    if phase == "PLANNED":
        return archetype == "planner" or rid.startswith(_PLANNED_SUBSTRATE_PREFIX)
    elif phase == "RED":
        return archetype == "tester" or rid in _RED_EXTRA_IDS
    elif phase == "GREEN":
        return archetype == "coder"
    elif phase == "SMOKE":
        return archetype == "tester"
    elif phase == "REFACTOR":
        return archetype == "coder" and rule.disposition == "strict"
    return False


def _select_toolkit_slice(
    phase: str,
    registry: List[RuleMetadata],
    override: Optional[Dict[str, List[str]]],
) -> List[RuleMetadata]:
    """Build the toolkit slice for *phase*, applying config override if present."""
    if isinstance(override, dict) and phase in override:
        override_ids = set(override[phase])
        return sorted(
            [r for r in registry if _is_toolkit_rule(r) and r.rule_id in override_ids],
            key=lambda r: r.rule_id,
        )

    return sorted(
        [r for r in registry if _is_toolkit_rule(r) and _toolkit_matches_phase(r, phase)],
        key=lambda r: r.rule_id,
    )


def _select_repo_slice(phase: str, registry: List[RuleMetadata]) -> List[RuleMetadata]:
    """Build the repo-rule slice per substrate v12 §8.1."""
    selected: List[RuleMetadata] = []
    seen: set = set()

    def _add(rule: RuleMetadata) -> None:
        if rule.rule_id not in seen:
            seen.add(rule.rule_id)
            selected.append(rule)

    # Phase-matched repo rules
    for rule in registry:
        if not rule.rule_id.startswith("repo."):
            continue
        if rule.phase and rule.phase.upper() == phase:
            _add(rule)

    # REFACTOR regression sweep: all strict-disposition repo rules
    if phase == "REFACTOR":
        for rule in registry:
            if rule.rule_id.startswith("repo.") and rule.disposition == "strict":
                _add(rule)

    selected.sort(key=lambda r: r.rule_id)
    return selected


def build_validator_set(
    phase: str,
    config: CoachConfig,
    registry: Optional[Iterable[RuleMetadata]] = None,
) -> ValidatorSet:
    """Build the validator set for the given coach phase.

    Args:
        phase: Coach phase (PLANNED, RED, GREEN, SMOKE, REFACTOR).
        config: Coach configuration with validator selection settings.
        registry: Optional iterable of RuleMetadata. Defaults to iter_rules().

    Returns:
        ValidatorSet with toolkit_slice and repo_slice.

    Raises:
        PhaseSelectionError: when phase is unknown.
    """
    phase_upper = _normalize_phase(phase)
    rules = list(registry) if registry is not None else list(iter_rules())

    selection = config.validators.selection
    override: Optional[Dict[str, List[str]]] = None
    if isinstance(selection, dict):
        override = selection

    toolkit_slice = tuple(_select_toolkit_slice(phase_upper, rules, override))
    repo_slice = tuple(_select_repo_slice(phase_upper, rules))

    return ValidatorSet(toolkit_slice=toolkit_slice, repo_slice=repo_slice)


__all__ = [
    "PhaseSelectionError",
    "VALID_PHASES",
    "ValidatorSet",
    "build_validator_set",
]
