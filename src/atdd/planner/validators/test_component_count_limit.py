# Phase: RED
# Layer: backend.integration
"""planner.component.count-limit validator (#1639).

A feature must declare at most 8 components; beyond 8 the feature is too large
and should be split. The subject is the ``components:`` block on
``plan/<wagon>/features/<feature>.yaml``, summed over every ``count:``.

Disposition is ``advisory``: the rule was declared by #1111 and enforced by
nothing, so the live corpus carries 13 features over the limit. Reporting that
debt is the point; blocking on it would be a gate nobody could land against.
Detection is proven by the synthetic unit tests below, not by the live scan.

Convention: src/atdd/planner/conventions/nodes/planner.component.count-limit.convention.yaml
Rule:       planner.component.count-limit
Run:        atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.validators._component_blocks import iter_feature_files, read_components

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.component.count-limit")
_VALIDATOR_ID = "component_count_limit"

MAX_COMPONENTS = 8

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"


def find_over_limit(feature: Path, total: int, *, root: Path) -> List[Violation]:
    """Zero or one violation for one feature's component total."""
    if total <= MAX_COMPONENTS:
        return []
    try:
        loc = str(feature.relative_to(root))
    except ValueError:
        loc = str(feature)
    return [
        Violation(
            rule_id=_RULE.rule_id,
            severity=_RULE.severity,
            location=f"{loc}:1",
            detail=(
                f"feature declares {total} components (limit {MAX_COMPONENTS}) — "
                f"split the feature"
            ),
            fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
        )
    ]


def _scan_live() -> List[Violation]:
    out: List[Violation] = []
    for feature in iter_feature_files(PLAN_DIR):
        _, total = read_components(feature)
        out.extend(find_over_limit(feature, total, root=REPO_ROOT))
    return out


def test_component_count_limit() -> None:
    """Live corpus: report every feature over the 8-component limit."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


# ---------------------------------------------------------------------------
# Detection proof — the live scan above cannot prove the rule bites, because a
# clean corpus and a broken detector look identical from outside.
# ---------------------------------------------------------------------------
def test_over_limit_is_flagged(tmp_path: Path) -> None:
    v = find_over_limit(tmp_path / "f.yaml", 9, root=tmp_path)
    assert len(v) == 1 and "9 components" in v[0].detail, v


def test_at_limit_passes(tmp_path: Path) -> None:
    assert find_over_limit(tmp_path / "f.yaml", MAX_COMPONENTS, root=tmp_path) == []


def test_no_components_passes(tmp_path: Path) -> None:
    assert find_over_limit(tmp_path / "f.yaml", 0, root=tmp_path) == []


def test_reader_sums_counts_across_sides_and_layers(tmp_path: Path) -> None:
    """The total is summed over every side/layer, not per-layer."""
    f = tmp_path / "feature.yaml"
    f.write_text(
        "components:\n"
        "  backend:\n"
        "    application:\n"
        "      - {type: use_cases, count: 2}\n"
        "    domain:\n"
        "      - {type: entities, count: 3}\n"
        "  frontend:\n"
        "    presentation:\n"
        "      - {type: views, count: 4}\n",
        encoding="utf-8",
    )
    entries, total = read_components(f)
    assert total == 9 and len(entries) == 3, (total, entries)
