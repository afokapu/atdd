"""Compose convention sources into one in-memory graph (#1206).

Minimal real loader: walks the plan/ convention sources (wagons, features, WMBTs)
and materializes one node per source document. The result exposes ``.nodes``
(list of node dicts) for template evaluators and the shadow harness. Traversal
edges are derived lazily by evaluators from node fields; this loader's job is
composition + node identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class ConventionGraph:
    nodes: List[dict] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> List[dict]:
        return [n for n in self.nodes if n.get("kind") == kind]


def _node_from_doc(doc: dict, path: Path, kind: str) -> dict:
    doc = doc if isinstance(doc, dict) else {}
    urn = doc.get("urn") or doc.get("wagon") or doc.get("id") or str(path)
    return {
        "id": urn,
        "kind": kind,
        "location": str(path),
        "fields": doc,
        "refs": doc.get("refs", []) or [],
    }


def _safe_node(path: Path, kind: str, g: "ConventionGraph") -> None:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        g.nodes.append(_node_from_doc(doc, path, kind))
    except yaml.YAMLError:
        g.nodes.append({"id": str(path), "kind": kind, "location": str(path),
                        "parse_error": "yaml parse failed"})


def load_composed_graph(repo_root) -> ConventionGraph:
    root = Path(repo_root)
    plan = root / "plan"
    g = ConventionGraph()
    if not plan.is_dir():
        return g
    for wagon_dir in sorted(p for p in plan.iterdir() if p.is_dir()):
        manifest = wagon_dir / f"_{wagon_dir.name}.yaml"
        if manifest.exists():
            _safe_node(manifest, "wagon", g)
        feats = wagon_dir / "features"
        if feats.is_dir():
            for feat in sorted(feats.glob("*.yaml")):
                _safe_node(feat, "feature", g)
        for wmbt in sorted(wagon_dir.glob("[A-Z]*.yaml")):
            _safe_node(wmbt, "wmbt", g)
    return g
