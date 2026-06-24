"""Compose the REAL convention graph + normalized indexes (#1206).

This is not a toy: it ingests the actual repo convention sources and normalizes
every node so template selectors can find eligible nodes:

  - wagons   (plan/<w>/_<w>.yaml)         kind="wagon"   .theme, refs -> feature urns
  - features (plan/<w>/features/*.yaml)   kind="feature" refs -> wmbt urns
  - wmbts    (plan/<w>/[A-Z]*.yaml)       kind="wmbt"
  - trains   (plan/_trains.yaml)          kind="train"   refs -> wagon urns
  - rules    (src/atdd/**/conventions/**/*.yaml: rules[])  kind="rule"  .validator
  - emitted rule_ids: bind_rule("<id>") across src/atdd/**/validators/**

Every node exposes: id, kind, package, source_path/location, fields, refs, theme.
The graph exposes nodes()/by_id()/by_kind()/refs_from()/rules()/emits().
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

_log = logging.getLogger(__name__)

_BIND_RULE_RE = re.compile(r'bind_rule\(\s*["\']([^"\']+)["\']')


@dataclass
class Node:
    id: str
    kind: str
    location: str
    package: Optional[str] = None
    theme: Optional[str] = None
    refs: List[str] = field(default_factory=list)        # outgoing target ids
    validator: Optional[str] = None                      # for rule nodes: "file::test"
    fields: dict = field(default_factory=dict)


@dataclass
class ConventionGraph:
    _nodes: List[Node] = field(default_factory=list)
    _by_id: Dict[str, Node] = field(default_factory=dict)
    _emits: Dict[str, Set[str]] = field(default_factory=dict)   # rule_id -> {validator file relpaths}
    _validator_stems: Set[str] = field(default_factory=set)     # {test_x, ...} present under validators/
    root: Optional[Path] = None

    def validator_stems(self) -> Set[str]:
        return set(self._validator_stems)

    # --- normalized interface (what selectors/traversals query) ---
    def nodes(self) -> List[Node]:
        return list(self._nodes)

    def by_kind(self, kind: str) -> List[Node]:
        return [n for n in self._nodes if n.kind == kind]

    def by_id(self, node_id: str) -> Optional[Node]:
        return self._by_id.get(node_id)

    def ids(self) -> Set[str]:
        return set(self._by_id)

    def refs_from(self, node: Node) -> List[str]:
        return list(node.refs)

    def rules(self) -> List[Node]:
        return self.by_kind("rule")

    def emits(self, rule_id: str) -> Set[str]:
        return self._emits.get(rule_id, set())

    def _add(self, n: Node) -> None:
        self._nodes.append(n)
        self._by_id.setdefault(n.id, n)


def _safe_yaml(path: Path) -> dict:
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except yaml.YAMLError as exc:
        # Tolerate malformed sources so composition continues; parse errors are
        # reported separately by scan_parse_errors(). Log — never silently swallow.
        _log.info("graph_loader skipped unparseable source",
                  extra={"path": str(path), "error": str(exc).splitlines()[0][:120]})
        return {}


def scan_parse_errors(repo_root) -> List[dict]:
    """Re-walk convention sources; report any that fail to parse (composition)."""
    root = Path(repo_root)
    errs: List[dict] = []
    sources = []
    plan = root / "plan"
    if plan.is_dir():
        sources += list(plan.rglob("*.yaml"))
    sources += list((root / "src" / "atdd").rglob("*.convention.yaml"))
    for p in sources:
        try:
            yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errs.append({"source_file": str(p.relative_to(root)),
                         "parse_error": str(exc).splitlines()[0][:120]})
    return errs


def load_composed_graph(repo_root) -> ConventionGraph:
    root = Path(repo_root)
    g = ConventionGraph(root=root)
    plan = root / "plan"

    # wagons / features / wmbts
    if plan.is_dir():
        for wdir in sorted(p for p in plan.iterdir() if p.is_dir()):
            slug = wdir.name
            man = wdir / f"_{slug}.yaml"
            if man.exists():
                d = _safe_yaml(man)
                g._add(Node(id=d.get("urn") or f"wagon:{d.get('wagon', slug)}",
                            kind="wagon", location=str(man.relative_to(root)),
                            package=slug, theme=d.get("theme"),
                            refs=[f.get("urn") for f in (d.get("features") or []) if f.get("urn")],
                            fields=d))
            fdir = wdir / "features"
            if fdir.is_dir():
                for f in sorted(fdir.glob("*.yaml")):
                    d = _safe_yaml(f)
                    g._add(Node(id=d.get("urn") or str(f), kind="feature",
                                location=str(f.relative_to(root)), package=slug,
                                refs=list(d.get("wmbts") or []), fields=d))
            for w in sorted(wdir.glob("[A-Z]*.yaml")):
                d = _safe_yaml(w)
                g._add(Node(id=d.get("urn") or str(w), kind="wmbt",
                            location=str(w.relative_to(root)), package=slug, fields=d))

    # trains: load the conformant DETAIL files (plan/_trains/*.yaml), not the
    # _trains.yaml index. refs = wagon participants (system:* terminals excluded).
    tdir = plan / "_trains"
    if tdir.is_dir():
        for tf in sorted(tdir.glob("*.yaml")):
            d = _safe_yaml(tf)
            if not d.get("train_id"):
                continue
            g._add(Node(id=f"train:{d['train_id']}", kind="train",
                        location=str(tf.relative_to(root)),
                        refs=[p for p in (d.get("participants") or [])
                              if isinstance(p, str) and p.startswith("wagon:")],
                        fields=d))

    # rules from convention sources
    for conv in sorted((root / "src" / "atdd").rglob("*.convention.yaml")):
        d = _safe_yaml(conv)
        for rule in (d.get("rules") or []):
            if not isinstance(rule, dict) or not rule.get("id"):
                continue
            g._add(Node(id=rule["id"], kind="rule",
                        location=str(conv.relative_to(root)),
                        validator=rule.get("validator"), fields=rule))

    # emitted rule_ids: bind_rule("<id>") across validator sources
    vroot = root / "src" / "atdd"
    for py in vroot.rglob("*.py"):
        if "/validators/" not in str(py):
            continue
        try:
            txt = py.read_text(encoding="utf-8")
        except OSError:
            continue
        g._validator_stems.add(py.stem)
        for rid in _BIND_RULE_RE.findall(txt):
            g._emits.setdefault(rid, set()).add(str(py.relative_to(root)))

    return g
