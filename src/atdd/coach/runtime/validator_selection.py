# URN: component:govern-lifecycle:enforcement-substrate:validator_selection:backend:domain
# Runtime: python
# Purpose: Per-phase validator selection per spec §6.5 (toolkit slice) and substrate v12 §8.1 (repo-rule slice).

"""Per-phase validator selection (spec §6.5, substrate v12 §8.1).

Public API:
  - build_validator_set(phase, config, registry) -> ValidatorSet
  - ValidatorSet (immutable)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple, Union

from atdd.coach.utils.coach_config import CoachConfig
from atdd.coach.utils.rule_binding import RuleMetadata


VALID_PHASES = ("PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR")


@dataclass(frozen=True)
class ValidatorSet:
    """Phase-selected validator set: toolkit slice ∪ repo-rule slice."""

    toolkit_slice: Tuple[RuleMetadata, ...]
    repo_slice: Tuple[RuleMetadata, ...]

    @property
    def all_rules(self) -> Tuple[RuleMetadata, ...]:
        return self.toolkit_slice + self.repo_slice


def build_validator_set(
    phase: str,
    config: CoachConfig,
    registry: Optional[Iterable[RuleMetadata]] = None,
) -> ValidatorSet:
    """Build the validator set for the given coach phase.

    Stub — will be implemented in GREEN phase.
    """
    raise NotImplementedError("validator_selection.build_validator_set not yet implemented")
