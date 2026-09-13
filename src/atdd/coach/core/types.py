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
from enum import Enum, StrEnum
from typing import Literal, Mapping

# --------------------------------------------------------------------------- #
# §4.1 Coach-core enums                                                        #
# --------------------------------------------------------------------------- #


class Phase(str, Enum):
    """The per-issue lifecycle vocabulary.

    SOURCE OF TRUTH: ``coach/conventions/phase_machine.convention.yaml``. These
    members MUST equal the phases that file declares. This is the one part of
    the lifecycle the convention does NOT fully own — #1946 projected the
    transition table, ``PLANNED_PATH``, the spine successor maps and the
    ``atdd:<PHASE>`` label set from the YAML, but kept this enum a literal so
    ~287 ``Phase.X`` sites across ``coach/``, ``train/`` and ``state/`` stay
    resolvable to the type checker (#1946 Decision 3).

    SO ADDING A PHASE IS TWO EDITS: the YAML, and one line here. Editing this
    list without the YAML, or the YAML without this list, is caught — not
    silently, and not only by a test: ``handlers/state_machine.py`` builds its
    transition table at import via ``Phase(name)``, so a mismatch raises
    ``ValueError`` and the coach runtime does not load. The tests that name the
    coupling are ``D004-UNIT-005::test_the_core_phase_enum_is_pinned_to_the_convention``,
    ``D004-UNIT-001::test_adding_a_phase_costs_exactly_one_python_edit`` and
    ``D004-SMOKE-001::test_every_declared_phase_is_nameable_by_the_shipped_runtime``.

    ``(str, Enum)`` with an explicit ``__str__``, NOT ``StrEnum`` — deliberately.
    ``pyrightconfig.json`` pins ``pythonVersion: "3.10"`` and ``enum.StrEnum``
    landed in 3.11, so under the repo's own type checker a ``StrEnum`` member
    degrades to a bare ``str`` literal: every ``dict[str, Phase]`` holding one
    then fails ``reportAssignmentType`` and every ``.value`` fails
    ``reportAttributeAccessIssue`` (43 findings when #1946 first collapsed the two
    enums onto this one). Raising the pinned version would invalidate the frozen
    baseline wholesale, which ``pyrightconfig.json`` forbids in its own comment.

    The two forms are behaviourally indistinguishable — measured across ``str``,
    f-string, ``%``, ``format``, ``json.dumps`` as value and as key, concatenation,
    both equality directions, hash-equality with ``str``, sort order, pickle,
    identity on construction, ``.value`` type and ``repr``.
    """

    INIT = "INIT"
    PLANNED = "PLANNED"
    RED = "RED"
    GREEN = "GREEN"
    SMOKE = "SMOKE"
    REFACTOR = "REFACTOR"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    OBSOLETE = "OBSOLETE"
    # Success without code (#1967): an umbrella that answered its question and
    # decomposed it into children. An escape, never a rung — see the convention.
    RESOLVED = "RESOLVED"

    def __str__(self) -> str:
        return self.value


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
