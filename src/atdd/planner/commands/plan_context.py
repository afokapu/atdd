"""atdd plan — working-context assembly (#1139 slice 6).

The harness's first job: assemble the agent's working context from the guideline
convention-nodes (the session-protocol `planner.plan.*` + the decomposition-
protocol `planner.decomposition.*` nodes) and the relationship edges among them
(the protocol flow). The conventions *are* the guidelines — `atdd plan` loads
and presents them; it does not restate them. Stdlib only.

The decomposition-protocol nodes ship via #761; until that merges, only the
session-protocol nodes are present — the assembler simply includes whatever
guideline nodes exist (forward-compatible).
"""
from __future__ import annotations

from pathlib import Path

import yaml

_GUIDELINE_PREFIXES = ("planner.plan.", "planner.decomposition.")


def _nodes_dir(root: Path | str) -> Path:
    return Path(root) / "src" / "atdd" / "planner" / "conventions" / "nodes"


def _graph(root: Path | str) -> Path:
    return Path(root) / "src" / "atdd" / "coach" / "graph" / "relationships.yaml"


def load_working_context(root: Path | str = ".") -> dict:
    """Return the agent's working context:
    {guidelines: {rule_id: {kind, statement, terms[]}}, edges: [{source,target,type,reason}]}.
    Only guideline nodes (session-protocol + decomposition-protocol) and the
    edges touching them are included."""
    guidelines: dict = {}
    nodes_dir = _nodes_dir(root)
    if nodes_dir.is_dir():
        for f in sorted(nodes_dir.glob("*.convention.yaml")):
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            rid = doc.get("rule_id", "")
            if isinstance(rid, str) and rid.startswith(_GUIDELINE_PREFIXES):
                guidelines[rid] = {
                    "kind": doc.get("kind"),
                    "statement": doc.get("statement"),
                    "terms": [t.get("term_id") for t in (doc.get("terms") or []) if isinstance(t, dict)],
                }

    edges: list = []
    graph = _graph(root)
    if graph.is_dir() is False and graph.exists():
        g = yaml.safe_load(graph.read_text(encoding="utf-8")) or {}
        for e in (g.get("edges") or []):
            src, tgt = e.get("source_ref"), e.get("target_ref")
            if src in guidelines or tgt in guidelines:
                edges.append({"source": src, "target": tgt, "type": e.get("type"), "reason": e.get("reason")})

    return {"guidelines": guidelines, "edges": edges}
