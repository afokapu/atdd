"""Reusable graph-question archetype for the `grammar` family (#1204)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='grammar',
        template_id='identifier_grammar_conformance',
        question='Does an identifier, URN, rule id, or node id follow canonical grammar?',
        selector='nodes with id/rule_id/urn/name fields',
        traversal='node -> identifier field -> grammar parser',
        invariant='parser accepts identifier and parsed parts match graph context',
        auto_capture='a new node is included if it declares a grammar-governed identifier field',
        failure_evidence=['node_id', 'field', 'value', 'grammar_name', 'parse_error'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ---------------------------------------------------------------------------
# Family-declared REAL-graph evaluators (#1212, decentralized discovery).
#
# `_support.evaluators._real_evaluators()` auto-discovers this dict and merges it
# over the built-ins WITHOUT any edit to the shared central map (conflict-free
# fan-out). Keyed by template_id; each fn is `(graph, config)` and runs over the
# real composed ConventionGraph. `config["variant"]` selects the per-variant
# grammar; an unknown/None variant falls back to the canonical real-graph
# identifier_grammar_conformance sentinel (the WMBT-urn grammar) so the variants
# already proven through that sentinel keep their exact behaviour.
# ---------------------------------------------------------------------------

# A tightly-scoped freedom-layer Bash entry: Bash(<cmd>:*) with a non-empty inner
# command and no nested parens — never bare ``Bash``, ``Bash(*)``, or ``Bash(:*)``.
# Mirrors the legacy E032 grammar (freedom_layer_validator._SCOPED_RE / smoke regex).
_BASH_SCOPE_RE = re.compile(r"^Bash\((?P<cmd>[^()]+):\*\)$")

# The convention source that declares spawn_time.freedom_layer as DATA (#1062/E031).
_SESSION_CONVENTION_REL = "src/atdd/coach/conventions/session.convention.yaml"


def _freedom_layer(graph) -> dict:
    """Read spawn_time.freedom_layer from the real convention source on disk
    (selector node — it is data, not a wagon/rule node)."""
    conv = Path(graph.root) / _SESSION_CONVENTION_REL
    try:
        data = yaml.safe_load(conv.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    return (data.get("spawn_time") or {}).get("freedom_layer") or {}


def _freedom_layer_bash_scope_grammar(graph, config=None):
    """grammar/freedom_layer_bash_scope_grammar — every ``spawn_time.freedom_layer``
    ``allowed_bash`` entry must conform to the ``Bash(<cmd>:*)`` scoping grammar
    (the legacy E032 unscoped-entry rule, over the real convention data)."""
    allowed_bash = list(_freedom_layer(graph).get("allowed_bash") or [])
    out = []
    for entry in allowed_bash:
        if _BASH_SCOPE_RE.match(str(entry)) is None:
            out.append({
                "node_id": _SESSION_CONVENTION_REL,
                "field": "spawn_time.freedom_layer.allowed_bash",
                "value": entry,
                "grammar_name": "freedom-layer-bash-scope",
                "parse_error": "unscoped/over-broad Bash entry: must be Bash(<cmd>:*)",
            })
    return out


def _identifier_grammar_conformance(graph, config=None):
    """Config-parameterized dispatch for the grammar/identifier_grammar_conformance
    template over the real composed graph."""
    variant = (config or {}).get("variant")
    if variant == "freedom_layer_bash_scope_grammar":
        return _freedom_layer_bash_scope_grammar(graph, config)
    # default / WMBT-vocabulary path: the canonical real-graph sentinel.
    from .._support import sentinels as S

    return S.identifier_grammar_conformance(graph).violations


REAL_EVALUATORS = {
    "identifier_grammar_conformance": _identifier_grammar_conformance,
}
