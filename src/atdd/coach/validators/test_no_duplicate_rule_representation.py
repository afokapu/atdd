# URN: component:govern-lifecycle:enforcement-substrate:no_duplicate_rule_representation:backend:domain
# Purpose: A migrated rule must have ONE authoritative representation (#1225).
"""Single-authoritative-representation guard (#1225).

A rule_id declared in BOTH a legacy monolith ``rules:[]`` block AND a ``nodes/``
single-node convention file is a duplicate. For migrated convention-node rules the
``nodes/`` file is canonical (it is what ``graph_loader`` resolves, what ``atdd
author`` writes, and — since #1225 — what ``bind_rule`` / ``build_registry`` read),
so the monolith ``rules:[]`` entry MUST be removed.

Also covers ALIAS collisions: a monolith block whose canonical id is now an
``aliases:`` entry on a renamed ``nodes/`` rule is the same duplication and must go.
"""
from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.coach]


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for anc in (here, *here.parents):
        if (anc / "plan").is_dir() and (anc / "src" / "atdd").is_dir():
            return anc
    raise RuntimeError(f"could not locate repo root from {here}")


def _safe_yaml(path: Path) -> dict:
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _monolith_rule_ids(root: Path) -> dict:
    ids: dict = {}
    for f in glob.glob(str(root / "src/atdd/*/conventions/*.convention.yaml")):
        rules = _safe_yaml(Path(f)).get("rules")
        items = rules if isinstance(rules, list) else (
            list(rules.values()) if isinstance(rules, dict) else []
        )
        for r in items:
            rid = r.get("id") if isinstance(r, dict) else None
            if rid:
                ids.setdefault(rid, f)
    return ids


def _nodes_ids_and_aliases(root: Path):
    ids: dict = {}
    aliases: dict = {}
    for f in glob.glob(str(root / "src/atdd/*/conventions/nodes/*.convention.yaml")):
        d = _safe_yaml(Path(f))
        rid = d.get("rule_id")
        if not rid:
            continue
        ids[rid] = f
        for a in ((d.get("metadata") or {}).get("aliases") or []):
            if isinstance(a, str) and a:
                aliases[a] = f
    return ids, aliases


def test_no_duplicate_rule_representation():
    root = _repo_root()
    mono = _monolith_rule_ids(root)
    node_ids, node_aliases = _nodes_ids_and_aliases(root)
    dups = sorted(set(mono) & (set(node_ids) | set(node_aliases)))
    assert not dups, (
        f"{len(dups)} rule(s) declared in BOTH a monolith rules:[] block AND a nodes/ "
        f"single-node file (as its rule_id or an alias). nodes/ is authoritative for "
        f"migrated rules (#1225) — remove the monolith rules:[] entry:\n"
        + "\n".join(
            f"  {r}  (monolith: {Path(mono[r]).relative_to(root)}; "
            f"nodes: {Path(node_ids.get(r) or node_aliases.get(r)).relative_to(root)})"
            for r in dups
        )
    )
