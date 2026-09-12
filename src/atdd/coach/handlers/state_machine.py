"""State-machine types extracted from coach.py (issue #591 split).

Defines:
    HandlerResult  — return type for all per-concern handle() stubs
    CoachContext   — frozen view of resolved Config passed to handlers
    Transition     — (src, dst) phase pair passed to handlers
    Phase          — per-issue lifecycle enum (spec §4.1)
    TRANSITION_TABLE — legal transitions
    can_transition — table lookup helper
    PLANNED_PATH   — canonical state sequence
    StateMachine   — per-issue state container
    initialize_state_machine — factory

All logic is unchanged from J1 (issue #496).  Children (#585-#590) fill in
the stub handle() functions in the sibling modules.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple, Optional

from atdd.coach.core.types import Phase
from atdd.coach.gate.phase_edges import phase_machine, spine


class HandlerResult(str, Enum):
    """Return value for every per-concern handle() stub."""

    NOOP = "NOOP"
    HANDLED = "HANDLED"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"


#: The per-issue lifecycle vocabulary. NOT defined here: this is
#: :class:`atdd.coach.core.types.Phase`, re-exported.
#:
#: Until #1946 this module defined a SECOND Phase enum carrying ``MERGED`` and
#: lacking ``OBSOLETE``, while ``core.types.Phase`` carried the convention's
#: vocabulary. Both are ``str`` mixins, so ``handlers.Phase.COMPLETE ==
#: core.types.Phase.COMPLETE`` was True and frozenset membership across the two
#: classes succeeded — only ``is`` could see the fork, which is why it survived
#: from #496 while ``Phase("OBSOLETE")`` raised on every live transition path.
Phase = Phase


#: Legal transitions, PROJECTED from ``phase_machine.convention.yaml`` — whose own
#: header says *add or change a phase HERE, never in Python*.
#:
#: Read at import. If the convention is unreadable this RAISES
#: :class:`~atdd.coach.gate.phase_edges.PhaseMachineUnavailable` and the coach
#: runtime does not load, which is deliberate and matches ``phase_edges``: a
#: hardcoded fallback is the second source of truth the convention forbids, and it
#: would fail OPEN at exactly the moment the two are most likely to disagree.
TRANSITION_TABLE: dict[Phase, set[Phase]] = {
    Phase(name): {Phase(target) for target in targets}
    for name, targets in phase_machine().items()
}


def can_transition(src: Phase, dst: Phase) -> bool:
    return dst in TRANSITION_TABLE[src]


#: The linear spine, projected via the one walker (``phase_edges.spine``).
#: Escapes are off the path by construction; the terminal is whatever the
#: convention's chain ends on.
PLANNED_PATH: tuple[Phase, ...] = tuple(Phase(name) for name in spine())


@dataclass
class StateMachine:
    """Per-issue state container. J1 ships the structure; transition
    handlers land in per-state issues across the J/K/L/M tracks."""

    issue_number: int
    phase: Phase = Phase.INIT
    history: list[Phase] = field(default_factory=list)


def initialize_state_machine(issue_number: int) -> StateMachine:
    return StateMachine(issue_number=issue_number, phase=Phase.INIT)


class Transition(NamedTuple):
    """(src, dst) pair passed to every per-concern handle() stub."""

    src: Phase
    dst: Phase


@dataclass
class CoachContext:
    """Frozen view of resolved CLI config passed to handler stubs.

    Children (#585-#590) will read fields relevant to their concern.
    J3 (#586) adds coach_run_id and runtime_dir for the decisions writer.
    """

    issue_number: int
    coach_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    runtime_dir: Optional[Path] = None
    dry_run: bool = False
    strict_deps: bool = False
    multiplexer: Optional[str] = None
    multiplexer_mode: str = "workspace"
    llm: Optional[str] = None
    persona_llm: dict[str, str] = field(default_factory=dict)
    # Per-phase LLM/adapter selection (issue #746), keyed by lowercase phase
    # label ("planned", "red", "green", "smoke", "refactor"). Takes precedence
    # over persona_llm so the coach can run, e.g., RED and SMOKE (both tester)
    # on different models.
    phase_llm: dict[str, str] = field(default_factory=dict)
    judge_llm: Optional[str] = None
    require_issue_review: str = "warn"
    review_phases: set[str] = field(default_factory=set)
    skip_review: bool = False
    risk_threshold_block: Optional[int] = None
    allow_stale_suppressions: bool = False
    resume: Optional[str] = None
    auto_merge: bool = False
    max_retries: Optional[int] = None
    escalation_channel: Optional[str] = None
    # Issue #730: the issue's single persistent cmux surface (ATDD<N>),
    # created at first spawn and reused — persona agent respawned in place —
    # for every later phase transition. None until the first spawn.
    issue_surface_ref: Optional[str] = None
    # Issue #734: explicit orchestration seams so callers (and hermetic
    # integration tests) inject collaborators by construction instead of
    # monkeypatching module globals. ``multiplexer_backend`` overrides
    # ``_resolve_multiplexer()``; ``worktree_override`` overrides the
    # GitHub-backed ``_resolve_worktree()``. Both None in production.
    multiplexer_backend: Any = None
    worktree_override: Optional[Path] = None
