# Phase: GREEN
# Layer: backend.integration
"""planner.wagon.coupling-complexity advisory reporter (#1145 Phase 2).

Computes each wagon's cross-wagon coupling complexity = fan_in x fan_out
(Henry-Kafura proxy) over the produce->consume artifact-NAME graph, and
reports wagons above a soft, config-driven threshold. ADVISORY (non-blocking)
— this is the runnable surface for the complexity model
(planner.wagon.complexity-model).

Convention: src/atdd/planner/conventions/nodes/planner.wagon.coupling-complexity.convention.yaml
Rule:       planner.wagon.coupling-complexity
Run:        atdd validate planner
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

# Reuse the produce/consume graph builders from the cycle validator (single source).
from atdd.planner.validators.test_no_cross_wagon_consume_cycle import (
    build_edges,
    load_manifests,
)

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.wagon.coupling-complexity")
_VALIDATOR_ID = "wagon_coupling_complexity"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"
_DEFAULT_THRESHOLD = 6


def coupling_threshold(repo_root: Path = REPO_ROOT) -> int:
    """Soft advisory threshold from .atdd/config.yaml (planner.wagon.coupling_complexity_threshold)."""
    try:
        cfg = yaml.safe_load((repo_root / ".atdd" / "config.yaml").read_text()) or {}
        val = ((cfg.get("planner") or {}).get("wagon") or {}).get(
            "coupling_complexity_threshold"
        )
        return int(val) if val is not None else _DEFAULT_THRESHOLD
    except Exception:
        return _DEFAULT_THRESHOLD


def compute_coupling(
    manifests: Dict[str, Dict[str, list]],
) -> Dict[str, Tuple[int, int, int]]:
    """wagon -> (fan_in, fan_out, complexity = fan_in * fan_out).

    fan_out(W) = # wagons that consume one of W's produced artifacts.
    fan_in(W)  = # wagons whose produced artifact W consumes.
    """
    edges = build_edges(manifests)  # producer-wagon -> {consumer-wagons}
    fan_out = {w: len(edges.get(w, ())) for w in manifests}
    fan_in = {w: 0 for w in manifests}
    for _producer, consumers in edges.items():
        for consumer in consumers:
            fan_in[consumer] = fan_in.get(consumer, 0) + 1
    return {
        w: (fan_in.get(w, 0), fan_out.get(w, 0), fan_in.get(w, 0) * fan_out.get(w, 0))
        for w in manifests
    }


def _scan(threshold: int) -> List[Violation]:
    out: List[Violation] = []
    for wagon, (fan_in, fan_out, cx) in sorted(compute_coupling(load_manifests(PLAN_DIR)).items()):
        if cx > threshold:
            wd = wagon.replace("-", "_")
            out.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"plan/{wd}/_{wd}.yaml:1",
                    detail=(
                        f"wagon coupling complexity {cx} (fan_in={fan_in} x fan_out={fan_out}) "
                        f"exceeds soft threshold {threshold} — review for SPLIT/MERGE"
                    ),
                )
            )
    return out


def test_wagon_coupling_complexity_reported() -> None:
    """Advisory report of over-threshold wagons (non-blocking — advisory disposition)."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan(coupling_threshold()))


def test_compute_coupling_metric() -> None:
    """RED guard: fan_in/fan_out/complexity computed correctly on a synthetic graph."""
    manifests = {
        "a": {"produce": ["x"], "consume": ["y"]},  # a produces x; consumes y
        "b": {"produce": ["y"], "consume": ["x"]},  # b produces y; consumes x  -> a<->b
        "c": {"produce": [], "consume": ["x"]},      # c consumes x (from a)
    }
    m = compute_coupling(manifests)
    assert m["a"] == (1, 2, 2), m.get("a")  # in: {b}; out: {b,c}; cx=2
    assert m["b"] == (1, 1, 1), m.get("b")  # in: {a}; out: {a}; cx=1
    assert m["c"] == (1, 0, 0), m.get("c")  # in: {a}; out: {};  cx=0
