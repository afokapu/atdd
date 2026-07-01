"""Reusable graph-question archetype for the `binding` family (#1204)."""
from __future__ import annotations

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='binding',
        template_id='declaration_to_implementation_binding',
        question='Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?',
        selector='rule/declaration nodes where enforcement requires implementation',
        traversal='declaration node -> implementation_ref -> implementation index',
        invariant='implementation exists and declares compatibility with the declaration',
        auto_capture='a new node is included if it declares enforcement=validator or equivalent implementation binding metadata',
        failure_evidence=['declaration_node', 'implementation_ref', 'missing_or_incompatible_implementation', 'declaration_location'],
    ),
    TemplateContract(
        family_id='binding',
        template_id='emitted_identity_roundtrip',
        question='Does implementation output round-trip to the declaring rule or node?',
        selector='implementations/validators that emit rule_ids or node_ids',
        traversal='declaration -> implementation -> emitted identity -> declaration index',
        invariant='emitted identity resolves back to the same declaring rule/node',
        auto_capture='a new node is included if its implementation declares emitted identities in standard metadata',
        failure_evidence=['declaration_id', 'implementation_id', 'emitted_identity', 'expected_identity', 'actual_resolved_target'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ---------------------------------------------------------------------------
# Family-declared real-graph evaluator (#1212 binding-variant wiring).
#
# The shared foundation sentinel `rule_validator_roundtrip` emits an
# `implementation_ref` evidence key that is OUTSIDE this template's declared
# `failure_evidence` vocabulary (which names `implementation_id`). Exposing the
# evaluator here — auto-discovered by `_support.evaluators._real_evaluators()` —
# lets the family keep the proven real-graph traversal while normalizing the
# evidence keys to a strict SUBSET of the `emitted_identity_roundtrip` contract,
# WITHOUT editing the shared central map (conflict-free fan-out per #1212).
# ---------------------------------------------------------------------------
def _emitted_identity_roundtrip(graph, config=None):
    """Real-graph emitted-identity roundtrip with template-conformant evidence.

    Reuses `_support.sentinels.rule_validator_roundtrip` (the canonical real-graph
    logic: a rule's declared validator must `bind_rule(rule.id)` so the emitted
    identity round-trips back to the declaring rule). Evidence keys are projected
    onto the template's `failure_evidence` so every dict is a strict subset.
    """
    from .._support import sentinels as S

    out = []
    for ev in S.rule_validator_roundtrip(graph).violations:
        out.append({
            "declaration_id": ev.get("declaration_id"),
            "implementation_id": ev.get("implementation_ref"),
            "emitted_identity": ev.get("emitted_identity"),
            "actual_resolved_target": ev.get("actual_resolved_target"),
        })
    return out


REAL_EVALUATORS = {
    "emitted_identity_roundtrip": _emitted_identity_roundtrip,
}
