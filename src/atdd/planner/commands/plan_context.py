"""atdd plan — working-context assembly (#1139 slice 6).

The harness's first job: assemble the agent's working context from the guideline
convention-nodes (the session-protocol `planner.plan.*` + the decomposition-
protocol `planner.decomposition.*` nodes) and the relationship edges among them
(the protocol flow). The conventions *are* the guidelines — `atdd plan` loads
and presents them; it does not restate them. Stdlib only.

The decomposition-protocol nodes ship via #761; until that merges, only the
session-protocol nodes are present — the assembler simply includes whatever
guideline nodes exist (forward-compatible).

Resolution falls back to the installed package (#1275): the nodes and the
relationship graph are read from the bundled `atdd` package when the repo has
no `src/atdd/` tree of its own, so `atdd plan guidelines` works in consumer
repos and not just the toolkit's own source checkout. Repo-vendored files
override the package; a missing graph degrades `edges` to `[]`.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_GUIDELINE_PREFIXES = ("planner.plan.", "planner.decomposition.")

# Package-relative fallbacks (#1275). plan_context.py lives at
# atdd/planner/commands/plan_context.py, so the bundled nodes are two levels up
# under conventions/nodes, and the relationship graph three levels up under
# coach/graph. These resolve in any consumer repo that pip-installs atdd, with
# no src/atdd/ tree of its own. atdd installs unzipped, so __file__ is a real
# path (no zip-import); importlib.resources is unneeded and graph/ is not a
# package anyway.
_PKG_NODES_DIR = Path(__file__).resolve().parent.parent / "conventions" / "nodes"
_PKG_GRAPH = Path(__file__).resolve().parents[2] / "coach" / "graph" / "relationships.yaml"


def _repo_nodes_dir(root: Path | str) -> Path:
    return Path(root) / "src" / "atdd" / "planner" / "conventions" / "nodes"


def _repo_graph(root: Path | str) -> Path:
    return Path(root) / "src" / "atdd" / "coach" / "graph" / "relationships.yaml"


def _nodes_dirs(root: Path | str) -> list[Path]:
    """Directories to read guideline nodes from, in ascending precedence: the
    bundled package nodes are the base; repo-vendored nodes override them. A
    consumer repo (no src/atdd/) gets the package set; the toolkit's own repo
    resolves to the same files for both, so it reads them once."""
    dirs: list[Path] = []
    if _PKG_NODES_DIR.is_dir():
        dirs.append(_PKG_NODES_DIR)
    repo = _repo_nodes_dir(root)
    if repo.is_dir() and (not dirs or repo.resolve() != _PKG_NODES_DIR.resolve()):
        dirs.append(repo)
    return dirs


def _graph_path(root: Path | str) -> Path | None:
    """Repo-vendored relationships.yaml wins; otherwise the bundled package copy;
    otherwise None (consumer repos without the bundled graph degrade to []
    edges)."""
    repo = _repo_graph(root)
    if repo.is_file():
        return repo
    if _PKG_GRAPH.is_file():
        return _PKG_GRAPH
    return None


def load_working_context(root: Path | str = ".") -> dict:
    """Return the agent's working context:
    {guidelines: {rule_id: {kind, statement, terms[]}}, edges: [{source,target,type,reason}]}.
    Only guideline nodes (session-protocol + decomposition-protocol) and the
    edges touching them are included. Resolution falls back to the installed
    package so consumer repos (no src/atdd/ tree) still get the bundled
    conventions; repo-vendored nodes override the package (#1275)."""
    guidelines = _load_guidelines(root)
    return {"guidelines": guidelines, "edges": _load_guideline_edges(root, guidelines)}


def _load_guidelines(root: Path | str) -> dict:
    """The guideline nodes (session-protocol + decomposition-protocol), keyed by
    rule_id. Repo-vendored nodes override the packaged ones (#1275)."""
    guidelines: dict = {}
    for nodes_dir in _nodes_dirs(root):
        for f in sorted(nodes_dir.glob("*.convention.yaml")):
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            rid = doc.get("rule_id", "")
            if not (isinstance(rid, str) and rid.startswith(_GUIDELINE_PREFIXES)):
                continue
            guidelines[rid] = {
                "kind": doc.get("kind"),
                "statement": doc.get("statement"),
                "terms": [t.get("term_id") for t in (doc.get("terms") or []) if isinstance(t, dict)],
            }
    return guidelines


def _load_guideline_edges(root: Path | str, guidelines: dict) -> list:
    """The relationship edges touching a guideline node."""
    graph = _graph_path(root)
    if graph is None:
        return []
    g = yaml.safe_load(graph.read_text(encoding="utf-8")) or {}
    edges: list = []
    for e in (g.get("edges") or []):
        src, tgt = e.get("source_ref"), e.get("target_ref")
        if src in guidelines or tgt in guidelines:
            edges.append({"source": src, "target": tgt, "type": e.get("type"), "reason": e.get("reason")})
    return edges
