# Component: component:atdd-plan-core:elicit-contract:Elicit:backend:domain
"""The actor-neutral `elicit` decision-turn contract (#1096a, ratified 2026-06-18).

A pure decision turn: present {context + options} -> receive {verdict} -> normalize.
One request, one response. NO process is spawned, run, resumed, or cancelled
(that is `drive`, out of scope). Decoupled from the #1096 hub runtime and its
adapters: consumers (atdd plan keep/pivot/kill #1139; the coach Feed #955/#966)
speak only this contract; the hub routes a request to the active adapter.

Neutral home (`atdd.runtime`) so both planner and coach may import it without a
cross-domain boundary violation. Stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class ElicitRole(str, Enum):
    """WHO participates in a decision turn (NOT an ATDD discipline)."""
    WORKER = "worker"        # performs delegated work; raises/receives a decision need
    CONDUCTOR = "conductor"  # coordinates the turn; asks/routes/records (does not necessarily answer)
    OPERATOR = "operator"    # the human/human-facing authority that resolves/confirms/overrides/cancels


class AtddRole(str, Enum):
    """Optional ATDD discipline metadata — never the participation enum."""
    PLANNER = "planner"
    TESTER = "tester"
    CODER = "coder"
    COACH = "coach"


class ElicitKind(str, Enum):
    PERMISSION = "permission"      # allow/block or constrained-action approval
    QUESTION = "question"          # info / choice / form
    CONFIRMATION = "confirmation"  # explicit lock/confirm boundary (e.g. #1139 confirm-before-author)


class ElicitRisk(str, Enum):
    SAFE = "safe"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"


class DefaultPolicy(str, Enum):
    BLOCK = "block"
    AUTO_ANSWER = "auto_answer"
    ESCALATE = "escalate"
    CANCEL = "cancel"


class ElicitStatus(str, Enum):
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Participant:
    """A decision-turn participant: an elicit role + optional ATDD discipline + a ref."""
    elicit_role: ElicitRole
    ref: str
    atdd_role: AtddRole | None = None


@dataclass(frozen=True)
class ElicitRequest:
    elicit_id: str                       # correlation + idempotency key
    origin: Participant                  # who raised it
    kind: ElicitKind
    prompt: str
    risk: ElicitRisk = ElicitRisk.UNKNOWN
    questions: list = field(default_factory=list)  # the #976 question object(s), reused verbatim
    default_policy: DefaultPolicy = DefaultPolicy.ESCALATE
    context: dict = field(default_factory=dict)    # opaque to the channel; no process/session semantics


@dataclass(frozen=True)
class ElicitResponse:
    elicit_id: str                       # echoes the request
    status: ElicitStatus
    resolved_by: Participant
    selections: list = field(default_factory=list)  # FLAT list of stable option labels/ids
    freeform: str | None = None
    rationale: str | None = None


class ElicitContractError(ValueError):
    """Raised when a request/response violates the #1096a contract invariants."""


def validate_selections(request: ElicitRequest, selections: list) -> None:
    """Flat-but-stable rule: each selection must be a stable, unique option id/label
    drawn from the request's questions — never ambiguous display text, never nested."""
    if any(not isinstance(s, str) for s in selections):
        raise ElicitContractError("selections must be a flat list of strings (no nesting)")
    if len(selections) != len(set(selections)):
        raise ElicitContractError("selection values must be unique within the response")
    allowed = {
        opt.get("label")
        for q in (request.questions or [])
        for opt in (q.get("options") or [])
    }
    if allowed:  # only enforce when the request enumerated options (choice/permission)
        unknown = [s for s in selections if s not in allowed]
        if unknown:
            raise ElicitContractError(f"selections not offered by the request: {unknown!r}")


class Elicit(Protocol):
    """One decision turn. Blocks until terminal. The caller never chooses the adapter."""

    def elicit(self, request: ElicitRequest) -> ElicitResponse: ...


class InlineClaudeElicitAdapter:
    """#1139's ship-first adapter: routes an elicit turn to a Claude-native resolver
    (AskUserQuestion at runtime), behind the same `elicit` interface. The resolver is
    injected so the contract is testable and so swapping to the #1096 hub's adapter
    set later is a no-op for callers. Multi-option `selections` are carried here and
    degrade on ACP (whose Elicitation is draft) — exactly why callers speak the
    contract, never AskUserQuestion directly.
    """

    def __init__(self, resolver):
        # resolver: Callable[[ElicitRequest], ElicitResponse]
        self._resolver = resolver

    def elicit(self, request: ElicitRequest) -> ElicitResponse:
        response = self._resolver(request)
        if response.elicit_id != request.elicit_id:
            raise ElicitContractError("response.elicit_id must echo the request")
        if response.status is ElicitStatus.RESOLVED:
            validate_selections(request, response.selections)
        return response
