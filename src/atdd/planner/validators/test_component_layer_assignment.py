# Phase: RED
# Layer: backend.integration
"""planner.component.layer-assignment validator (#1639).

A component's layer must be one the catalog declares for its side: backend and
frontend each own presentation / application / domain / integration. This is the
narrower structural half of the catalog rule — it judges the ``side.layer``
coordinate only, so a feature naming a legitimate-but-uncatalogued *type* under
a valid layer is not double-reported here.

Disposition is ``advisory``: the live corpus carries 7 violations — one
``backend.assembly`` entry, and six components under sides the catalog never
defined (``devops``, ``hooks``, ``docs``) that are additionally authored without
any layer at all. Whether those sides should join the catalog or leave the
corpus is a decision this rule surfaces rather than forces.

Convention: src/atdd/planner/conventions/nodes/planner.component.layer-assignment.convention.yaml
Rule:       planner.component.layer-assignment
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
    LAYER_ABSENT,
    ComponentEntry,
    iter_feature_files,
    load_catalog,
    read_components,
)

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.component.layer-assignment")
_VALIDATOR_ID = "component_layer_assignment"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"


def find_bad_layers(
    entries: Sequence[ComponentEntry],
    catalog: Dict[str, Dict[str, Set[str]]],
    *,
    root: Path,
) -> List[Violation]:
    """One violation per distinct (feature, side, layer) the catalog rejects.

    Deduplicated per coordinate: a feature declaring six types under one bad
    layer has one layer problem, not six.
    """
    if not catalog:
        return []
    out: List[Violation] = []
    seen = set()
    for e in entries:
        layers = catalog.get(e.side)
        if layers is not None and e.layer in layers:
            continue
        key = (e.feature, e.side, e.layer)
        if key in seen:
            continue
        seen.add(key)
        try:
            loc = str(e.feature.relative_to(root))
        except ValueError:
            loc = str(e.feature)
        if e.layer == LAYER_ABSENT:
            detail = (
                f"component under side '{e.side}' declares no layer — every "
                f"component belongs to exactly one layer"
            )
        elif layers is None:
            detail = (
                f"side '{e.side}' is not a catalogued component side "
                f"(expected one of {sorted(catalog)})"
            )
        else:
            detail = (
                f"layer '{e.layer}' is not valid for side '{e.side}' "
                f"(expected one of {sorted(layers)})"
            )
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
        out.extend(find_bad_layers(entries, catalog, root=REPO_ROOT))
    return out


def test_component_layer_assignment() -> None:
    """Live corpus: report every component side/layer the catalog rejects."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


# ---------------------------------------------------------------------------
# Detection proof
# ---------------------------------------------------------------------------
_CATALOG = {
    "backend": {"domain": {"entities"}, "application": {"use_cases"}},
    "frontend": {"presentation": {"views"}},
}


def _entry(side: str, layer: str, tmp_path: Path, type_name: str = "entities") -> ComponentEntry:
    return ComponentEntry(tmp_path / "f.yaml", side, layer, type_name, 1)


def test_valid_layer_passes(tmp_path: Path) -> None:
    assert find_bad_layers([_entry("backend", "domain", tmp_path)], _CATALOG, root=tmp_path) == []


def test_invalid_layer_is_flagged(tmp_path: Path) -> None:
    v = find_bad_layers([_entry("backend", "assembly", tmp_path)], _CATALOG, root=tmp_path)
    assert len(v) == 1 and "layer 'assembly' is not valid" in v[0].detail, v


def test_unknown_side_is_flagged(tmp_path: Path) -> None:
    v = find_bad_layers([_entry("devops", "domain", tmp_path)], _CATALOG, root=tmp_path)
    assert len(v) == 1 and "side 'devops'" in v[0].detail, v


def test_bad_layer_reported_once_per_coordinate(tmp_path: Path) -> None:
    """Six bad types under one bad layer is one layer problem."""
    entries = [_entry("backend", "assembly", tmp_path, f"t{i}") for i in range(6)]
    assert len(find_bad_layers(entries, _CATALOG, root=tmp_path)) == 1


def test_uncatalogued_type_under_valid_layer_is_not_flagged_here(tmp_path: Path) -> None:
    """Type-level problems belong to planner.component.type-catalog, not here."""
    e = _entry("backend", "domain", tmp_path, type_name="adapters")
    assert find_bad_layers([e], _CATALOG, root=tmp_path) == []


def test_unreadable_catalog_judges_nothing(tmp_path: Path) -> None:
    assert find_bad_layers([_entry("backend", "nope", tmp_path)], {}, root=tmp_path) == []


def test_layerless_shape_is_reported_not_skipped(tmp_path: Path) -> None:
    """REGRESSION: the corpus carries `{side: [items]}` with no layer key. An
    earlier reader skipped that shape entirely, so six real entries were
    invisible to every component rule. Absence of a layer is a violation, not a
    reason to look away."""
    f = tmp_path / "feature.yaml"
    f.write_text(
        "components:\n"
        "  devops:\n"
        "    - {type: ci_workflows, count: 2}\n",
        encoding="utf-8",
    )
    entries, total = read_components(f)
    assert total == 2, total
    assert [e.layer for e in entries] == [LAYER_ABSENT], entries
    v = find_bad_layers(entries, _CATALOG, root=tmp_path)
    assert len(v) == 1 and "declares no layer" in v[0].detail, v
