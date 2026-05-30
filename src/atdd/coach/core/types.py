"""Coach-core typed contracts (frozen).

Single source of the typed surface every other Coach decomposition layer
consumes. Defined in the pure-policy module so the dependency direction points
inward (docs/coach-decomposition.md §4.1–§4.2, §3.3).

PURITY CONTRACT: this module imports stdlib typing primitives ONLY. It MUST NOT
import ``subprocess``, ``threading``, ``asyncio``, networking, ``gh``/``git``/
``cmux``, or any ``atdd.runtime``/``atdd.integrations``/``atdd.train``/
``atdd.observer`` module. Enforced by the import-discipline test (Child 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Mapping

# --------------------------------------------------------------------------- #
# §4.1 Coach-core enums                                                        #
# --------------------------------------------------------------------------- #


class Phase(StrEnum):
    INIT = "INIT"
    PLANNED = "PLANNED"
    RED = "RED"
    GREEN = "GREEN"
    SMOKE = "SMOKE"
    REFACTOR = "REFACTOR"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    OBSOLETE = "OBSOLETE"


class Persona(StrEnum):
    PLANNER = "planner"
    TESTER = "tester"
    CODER = "coder"
    REVIEWER = "reviewer"


class IssueType(StrEnum):
    IMPLEMENTATION = "implementation"
    FIX = "fix"
    CHORE = "chore"
    REFACTOR = "refactor"
    CLEANUP = "cleanup"
    DOCS = "docs"


class CiState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NONE = "none"


class VerdictKind(StrEnum):
    PROCEED = "proceed"   # advance to to_phase, dispatch persona
    STAY = "stay"         # remain in current phase; e.g. waiting on CI
    BLOCKED = "blocked"   # cannot advance; operator surface; do not retry
    ESCALATE = "escalate"  # operator MUST intervene; pause run


# --------------------------------------------------------------------------- #
# §4.2 Coach-core data types                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WmbtRef:
    wmbt_id: str                  # e.g. "wmbt:govern-lifecycle:E032"
    wagon: str
    acceptances: tuple[str, ...]  # urn strings


@dataclass(frozen=True)
class ValidatorReport:
    validator_id: str             # e.g. "issue_body_has_graph_context"
    rule_id: str                  # canonical rule id
    severity: int                 # 0-5
    disposition: str              # "block" | "warn-and-log" | "suppress-and-clean"
    unsuppressed_count: int       # how many violations remain after suppress markers
    location: str | None = None   # file:line or external ref
    detail: str | None = None     # short human-readable
    fix_hint_ref: str | None = None


@dataclass(frozen=True)
class CheckRun:
    name: str
    conclusion: Literal[
        "SUCCESS", "FAILURE", "NEUTRAL", "CANCELLED", "TIMED_OUT", "PENDING", "NONE"
    ]
    workflow_id: int | None


@dataclass(frozen=True)
class Review:
    reviewer: str
    state: Literal["APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"]
    submitted_at: str             # ISO-8601


@dataclass(frozen=True)
class PrState:
    number: int
    state: Literal["OPEN", "MERGED", "CLOSED"]
    mergeable: Literal["MERGEABLE", "CONFLICTING", "UNKNOWN"]
    merge_state: Literal["CLEAN", "BLOCKED", "BEHIND", "UNSTABLE", "DIRTY", "UNKNOWN"]
    head_sha: str
    check_runs: tuple[CheckRun, ...]
    reviews: tuple[Review, ...]
    closes_issues: tuple[int, ...]


@dataclass(frozen=True)
class Evidence:
    """Everything Coach needs to decide, materialized by train.persistence at one instant."""

    issue_number: int
    issue_type: IssueType
    current_phase: Phase
    train_id: str | None
    branch: str
    wmbts: tuple[WmbtRef, ...]
    validator_reports: tuple[ValidatorReport, ...]
    ci_state: CiState
    pr_state: PrState | None
    last_commit_sha: str
    artifacts_present: frozenset[str]   # e.g. {"PLAN_COMMIT", "RED_TESTS", ...}
    elapsed_in_phase_seconds: int
    conventions_hash: str               # ties Evidence to a Conventions snapshot


@dataclass(frozen=True)
class Verdict:
    kind: VerdictKind
    reason: str                  # human-readable; surfaced to operator
    rule_ids: tuple[str, ...]    # conventions that justify this verdict
    fix_hint: str | None = None  # for BLOCKED / ESCALATE: actionable next step
    retry_after_seconds: int | None = None  # for STAY: optional backoff hint


@dataclass(frozen=True)
class TransitionDecision:
    from_phase: Phase
    to_phase: Phase | None        # None when verdict.kind != PROCEED
    persona: Persona | None       # who runs next; None when not PROCEED
    prompt_template_id: str | None
    evidence_keys_required: tuple[str, ...]  # what evidence the worker will need
    verdict: Verdict              # PROCEED ⇒ dispatch; others ⇒ train runner surfaces


@dataclass(frozen=True)
class MergeVerdict:
    can_merge: bool
    blockers: tuple[str, ...]     # validator IDs or lifecycle reasons
    required_label: Phase | None  # e.g. REFACTOR or COMPLETE before merge


@dataclass(frozen=True)
class PhaseSpec:
    name: Phase
    agent: Persona | None
    transitions_to: tuple[Phase, ...]
    pre_commit_gate: str | None   # CLI command if any


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    severity: int
    disposition: str
    fix_hint: str


@dataclass(frozen=True)
class Conventions:
    """The frozen policy bundle Coach-core needs. Loaded by train.persistence."""

    phase_machine: Mapping[Phase, PhaseSpec]
    rules: Mapping[str, RuleSpec]
    prompt_templates: Mapping[str, str]   # template_id → fully rendered text
    snapshot_hash: str                    # sha256 of normalized source files
    snapshot_paths: tuple[str, ...]       # source files contributing to the snapshot


__all__ = [
    "Phase",
    "Persona",
    "IssueType",
    "CiState",
    "VerdictKind",
    "WmbtRef",
    "ValidatorReport",
    "CheckRun",
    "Review",
    "PrState",
    "Evidence",
    "Verdict",
    "TransitionDecision",
    "MergeVerdict",
    "PhaseSpec",
    "RuleSpec",
    "Conventions",
]
