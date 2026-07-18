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
from typing import List

import pytest
import yaml

from atdd.coach.utils.config import get_code_roots, load_atdd_config
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]


def _convention_roots() -> List[Path]:
    """Directories whose ``<archetype>/conventions/`` trees hold rule declarations.

    Config-driven per #1476/#1485: every root declared in ``.atdd/config.yaml``'s
    ``code:`` block is a candidate. ``code.toolkit`` is only present when a repo
    declares it (``get_code_roots`` never seeds it), so the atdd repo scans
    ``src/atdd`` because its OWN config says so — not because a validator knows
    the toolkit's layout. A repo that declares no root holding conventions simply
    yields nothing to scan.
    """
    repo_root = find_repo_root()
    config = load_atdd_config(repo_root)
    roots = []
    for rel in get_code_roots(config).values():
        root = rel if rel.is_absolute() else (repo_root / rel)
        if root.is_dir():
            roots.append(root)
    return roots


def _display(path: str) -> str:
    """Render *path* relative to the repo root when it sits inside it."""
    p = Path(path)
    try:
        return str(p.relative_to(find_repo_root()))
    except ValueError:
        return str(p)


def _safe_yaml(path: Path) -> dict:
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _monolith_rule_ids(roots: List[Path]) -> dict:
    ids: dict = {}
    for root in roots:
        for f in glob.glob(str(root / "*/conventions/*.convention.yaml")):
            rules = _safe_yaml(Path(f)).get("rules")
            items = rules if isinstance(rules, list) else (
                list(rules.values()) if isinstance(rules, dict) else []
            )
            for r in items:
                rid = r.get("id") if isinstance(r, dict) else None
                if rid:
                    ids.setdefault(rid, f)
    return ids


def _nodes_ids_and_aliases(roots: List[Path]):
    ids: dict = {}
    aliases: dict = {}
    for root in roots:
        for f in glob.glob(str(root / "*/conventions/nodes/*.convention.yaml")):
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
    roots = _convention_roots()
    mono = _monolith_rule_ids(roots)
    node_ids, node_aliases = _nodes_ids_and_aliases(roots)

    # Skip on ABSENCE OF SUBJECT, never on identity of repo: duplication is a
    # relation between a monolith ``rules:[]`` block and a ``nodes/`` file. With
    # neither kind of declaration present there is no relation to violate. A repo
    # that declares only one of the two still runs the assertion below (the
    # intersection is simply empty), so this cannot mask a real duplicate.
    if not mono and not node_ids and not node_aliases:
        pytest.skip(
            "no convention rule declarations under the declared code roots "
            f"({', '.join(str(r) for r in roots) or 'none'}) — nothing to check"
        )

    dups = sorted(set(mono) & (set(node_ids) | set(node_aliases)))
    assert not dups, (
        f"{len(dups)} rule(s) declared in BOTH a monolith rules:[] block AND a nodes/ "
        f"single-node file (as its rule_id or an alias). nodes/ is authoritative for "
        f"migrated rules (#1225) — remove the monolith rules:[] entry:\n"
        + "\n".join(
            f"  {r}  (monolith: {_display(mono[r])}; "
            f"nodes: {_display(node_ids.get(r) or node_aliases.get(r))})"
            for r in dups
        )
    )
