# URN: component:govern-lifecycle:define-transition-autonomy:c027_autonomy_claim:backend:unit
# Runtime: python
# Purpose: Resolve the node's claim about its own consumption against the gate's actual consumption (#1981).

"""Does the convention node's claim about `autonomy` match what the runtime does?

Two independent readings, deliberately kept apart:

* CLAIMED consumption is read from the node's own prose and metadata. A node that
  says nothing reads the key, or that a permissive declaration can at worst submit
  a rejected command, or that carries `disposition: documentation-only`, is
  claiming the axis binds no behaviour.
* ACTUAL consumption is read BEHAVIOURALLY, by running the gate check on an edge
  whose FROM phase declares `autonomy: agent` and seeing whether the verdict turns
  on that declaration. Not by grepping source: a grep for `declared_autonomy`
  would pass on an import nobody calls, and the question is whether the key
  reaches a verdict, not whether a name appears in a file.

The guard fails when the two disagree IN EITHER DIRECTION, because either side can
move. #1798 moved the runtime and left the prose; a later issue could equally
remove the waiver and leave a node claiming it exists. Both are the same defect —
a declaration that does not describe the system — and a guard that only watches one
side would have caught neither.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

#: Phrases that assert the key binds no behaviour. Matched case-insensitively on
#: the node's concatenated prose. These are the exact sentences #1626 authored and
#: #1798 falsified; pinning the strings is what makes the guard a tripwire on THIS
#: claim rather than a vague style check.
INERTNESS_CLAIMS = (
    "nothing reads the key",
    "can at worst submit a command atdd then rejects",
    "bounds the risk of a permissive declaration to a rejected command",
)

#: The disposition that declares a node binds no validator.
#:
#: NOT an inertness signal, and C027 first treated it as one. `documentation-only`
#: says this NODE declares no `validator:` back-reference — a fact about the node's
#: enforcement machinery. Whether a runtime reads the KEY is a separate question,
#: and the repo's reverse rule-coherence check enforces the distinction: any other
#: disposition demands a `validator:` field, which would make this principle a rule.
#: So the guard reads the PROSE, and the disposition is checked only for the false
#: JUSTIFICATION that #1626 attached to it.
DOCUMENTATION_ONLY = "documentation-only"

#: The justification #1626 gave for `documentation-only`, which #1798 falsified.
#: Matched against the file's raw text, because YAML comments do not survive a parse.
STALE_JUSTIFICATIONS = (
    "declarative first. the axis is declared and reviewable",
    "needs no bind_rule callsite",
)


@dataclass(frozen=True)
class ClaimVerdict:
    """Whether claim and consumption agree, and which side moved when they do not."""

    agrees: bool
    claims_unread: bool
    actually_read: bool
    detail: str

    def __bool__(self) -> bool:
        return self.agrees


def node_prose(node: Dict[str, Any]) -> str:
    """Every free-text field of the node, lower-cased and concatenated.

    `terms` is included: `legality_stays_with_atdd` restates the blast-radius
    claim in its own words, so a fix that edited only `statement` would leave the
    same false assertion standing one field over.
    """
    parts = [str(node.get(k) or "") for k in ("statement", "rationale", "notes")]
    for term in node.get("terms") or []:
        if isinstance(term, dict):
            parts.append(str(term.get("text") or ""))
    return "\n".join(parts).lower()


def claims_key_is_unread(node: Dict[str, Any]) -> bool:
    """True when the node's PROSE asserts the axis binds no behaviour.

    Deliberately does not consult `disposition`: see DOCUMENTATION_ONLY. A node may
    correctly declare it binds no validator while correctly describing a runtime
    that reads its key, and a guard that conflated the two would demand a change
    the repo's own coherence rule forbids.
    """
    return any(claim in node_prose(node) for claim in INERTNESS_CLAIMS)


def stale_justifications_in(raw_text: str) -> list:
    """Justification comments that rest on the falsified inertness claim."""
    lowered = raw_text.lower()
    return [j for j in STALE_JUSTIFICATIONS if j in lowered]


def gate_reads_autonomy(check: Optional[Any] = None) -> bool:
    """True when the approval gate's verdict TURNS ON the declared autonomy.

    Behavioural, not structural: the check is run on an edge whose FROM phase
    declares `autonomy: agent`, with no token anywhere, and again on one declaring
    `operator`. If the first is waived and the second is not, the key reached a
    verdict. A check that ignored the key would refuse both.
    """
    from atdd.coach.gate.decision import GateContext, GateVerdict

    if check is None:
        from atdd.coach.gate.approval_check import ApprovalTokenGateCheck

        check = ApprovalTokenGateCheck()

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        worktree = Path(tmp)
        agent_edge = check.run(GateContext(
            issue_number=424242, from_phase="SMOKE", to_phase="REFACTOR", worktree=worktree,
        ))
        operator_edge = check.run(GateContext(
            issue_number=424242, from_phase="PLANNED", to_phase="RED", worktree=worktree,
        ))

    waived = getattr(agent_edge, "verdict", None) == GateVerdict.NOT_APPLICABLE
    still_demanded = getattr(operator_edge, "verdict", None) != GateVerdict.NOT_APPLICABLE
    return bool(waived and still_demanded)


def load_node(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text()) or {}


def resolve_claim(node: Dict[str, Any], check: Optional[Any] = None) -> ClaimVerdict:
    """Compare the node's claim against the gate's behaviour and name the gap."""
    claims_unread = claims_key_is_unread(node)
    actually_read = gate_reads_autonomy(check)

    if claims_unread and actually_read:
        return ClaimVerdict(
            False, claims_unread, actually_read,
            "THE RUNTIME MOVED: the node claims the autonomy key binds no behaviour "
            "(an inertness phrase, or `disposition: documentation-only`), but the "
            "approval gate's verdict turns on it — an `autonomy: agent` edge is "
            "waived while an `operator` edge is still refused. Correct the node to "
            "name its reader, or remove the waiver.",
        )
    if not claims_unread and not actually_read:
        return ClaimVerdict(
            False, claims_unread, actually_read,
            "THE NODE MOVED: the node no longer claims the autonomy key is inert, "
            "but the approval gate's verdict does not turn on it — the waiver is "
            "gone or no longer keys on `autonomy: agent`. Restore the waiver, or "
            "restore the node's inertness claim.",
        )
    return ClaimVerdict(
        True, claims_unread, actually_read,
        "claim and consumption agree: the node "
        + ("claims inert and nothing reads it" if claims_unread
           else "describes a reader and the gate reads it"),
    )
