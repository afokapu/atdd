# Phase: RED
# Layer: backend.integration
"""planner.component.type-catalog validator (#1639).

Every ``type:`` declared in a feature's ``components:`` block must exist in the
canonical component type catalog, under the same side and layer. The catalog is
read from the ``planner.component.type-catalog`` node's terms — the node is the
authority, so adding a type is a convention edit, not a validator edit.

Disposition is ``advisory``: the catalog was declared by #1111 and enforced by
nothing, so the live corpus carries 92 entries naming types the catalog does
not list (``adapters``, ``schemas``, ``prompts``, ``ci_gates``, ...). Several are
plainly legitimate and belong in the catalog; that triage is the follow-up this
rule exists to make visible, which is why it reports rather than blocks.

Convention: src/atdd/planner/conventions/nodes/planner.component.type-catalog.convention.yaml
Rule:       planner.component.type-catalog
Run:        atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Set

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.validators._component_blocks import (
    ComponentEntry,
    iter_feature_files,
    load_catalog,
    read_components,
)

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.component.type-catalog")
_VALIDATOR_ID = "component_type_catalog"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"


def find_uncatalogued(
    entries: Sequence[ComponentEntry],
    catalog: Dict[str, Dict[str, Set[str]]],
    *,
    root: Path,
) -> List[Violation]:
    """One violation per entry whose (side, layer, type) is not in *catalog*.

    An empty catalog means the node could not be read; that is a reason to judge
    nothing, not to condemn everything.
    """
    if not catalog:
        return []
    out: List[Violation] = []
    for e in entries:
        layers = catalog.get(e.side)
        if layers is None:
            detail = f"side '{e.side}' is not in the component type catalog"
        elif e.layer not in layers:
            detail = f"layer '{e.side}.{e.layer}' is not in the component type catalog"
        elif e.type_name not in layers[e.layer]:
            detail = (
                f"component type '{e.type_name}' is not catalogued under "
                f"{e.side}.{e.layer}"
            )
        else:
            continue
        try:
            loc = str(e.feature.relative_to(root))
        except ValueError:
            loc = str(e.feature)
        out.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{loc}:1",
                detail=detail,
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
    return out


def _scan_live() -> List[Violation]:
    catalog = load_catalog()
    out: List[Violation] = []
    for feature in iter_feature_files(PLAN_DIR):
        entries, _ = read_components(feature)
        out.extend(find_uncatalogued(entries, catalog, root=REPO_ROOT))
    return out


def test_component_type_catalog() -> None:
    """Live corpus: report every component type absent from the catalog."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


# ---------------------------------------------------------------------------
# Detection proof
# ---------------------------------------------------------------------------
_CATALOG = {"backend": {"domain": {"entities"}}, "frontend": {"presentation": {"views"}}}


def _entry(side: str, layer: str, type_name: str, tmp_path: Path) -> ComponentEntry:
    return ComponentEntry(tmp_path / "f.yaml", side, layer, type_name, 1)


def test_catalogued_type_passes(tmp_path: Path) -> None:
    e = _entry("backend", "domain", "entities", tmp_path)
    assert find_uncatalogued([e], _CATALOG, root=tmp_path) == []


def test_unknown_type_is_flagged(tmp_path: Path) -> None:
    e = _entry("backend", "domain", "adapters", tmp_path)
    v = find_uncatalogued([e], _CATALOG, root=tmp_path)
    assert len(v) == 1 and "'adapters' is not catalogued" in v[0].detail, v


def test_unknown_layer_is_flagged(tmp_path: Path) -> None:
    e = _entry("backend", "assembly", "entities", tmp_path)
    v = find_uncatalogued([e], _CATALOG, root=tmp_path)
    assert len(v) == 1 and "backend.assembly" in v[0].detail, v


def test_unknown_side_is_flagged(tmp_path: Path) -> None:
    e = _entry("devops", "domain", "entities", tmp_path)
    v = find_uncatalogued([e], _CATALOG, root=tmp_path)
    assert len(v) == 1 and "side 'devops'" in v[0].detail, v


def test_unreadable_catalog_judges_nothing(tmp_path: Path) -> None:
    """No catalog -> no verdict. Absence of the authority is not a violation."""
    e = _entry("backend", "domain", "whatever", tmp_path)
    assert find_uncatalogued([e], {}, root=tmp_path) == []


def test_real_catalog_node_is_readable() -> None:
    """The shipped node must actually parse into a catalog — otherwise the live
    scan above would silently judge nothing and pass vacuously forever."""
    catalog = load_catalog()
    assert catalog.get("backend", {}).get("domain"), catalog.keys()
    assert "entities" in catalog["backend"]["domain"]
    assert catalog.get("frontend", {}).get("presentation")
