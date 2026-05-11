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
from typing import NamedTuple, Optional


class HandlerResult(str, Enum):
    """Return value for every per-concern handle() stub."""

    NOOP = "NOOP"
    HANDLED = "HANDLED"
    ERROR = "ERROR"


class Phase(str, Enum):
    """Per-issue lifecycle states (spec §4.1).

    `str` mixin gives a stable string serialization for the eventual
    decision-log writer (#J3); J1 itself never writes the log.
    """

    INIT = "INIT"
    PLANNED = "PLANNED"
    RED = "RED"
    GREEN = "GREEN"
    SMOKE = "SMOKE"
    REFACTOR = "REFACTOR"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    MERGED = "MERGED"

    def __str__(self) -> str:
        return self.value


TRANSITION_TABLE: dict[Phase, set[Phase]] = {
    Phase.INIT:     {Phase.PLANNED, Phase.BLOCKED},
    Phase.PLANNED:  {Phase.RED, Phase.BLOCKED},
    Phase.RED:      {Phase.GREEN, Phase.BLOCKED},
    Phase.GREEN:    {Phase.SMOKE, Phase.BLOCKED},
    Phase.SMOKE:    {Phase.REFACTOR, Phase.BLOCKED},
    Phase.REFACTOR: {Phase.COMPLETE, Phase.BLOCKED},
    Phase.COMPLETE: {Phase.MERGED},
    Phase.BLOCKED:  {
        Phase.INIT, Phase.PLANNED, Phase.RED,
        Phase.GREEN, Phase.SMOKE, Phase.REFACTOR,
    },
    Phase.MERGED:   set(),
}


def can_transition(src: Phase, dst: Phase) -> bool:
    return dst in TRANSITION_TABLE[src]


PLANNED_PATH: tuple[Phase, ...] = (
    Phase.INIT, Phase.PLANNED, Phase.RED, Phase.GREEN,
    Phase.SMOKE, Phase.REFACTOR, Phase.COMPLETE, Phase.MERGED,
)


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
