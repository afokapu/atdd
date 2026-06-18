# Phase: GREEN
# Layer: backend.integration
"""planner.wagon.separability advisory validator (#1147 Phase 2).

Runs the WMBT-level cohesion/coupling metric (_wagon_cohesion) on the live
plan/ corpus and emits an ADVISORY [MERGE] finding for any wagon whose
internal cohesion is below its tightest single-neighbor coupling. Non-blocking.

Token vocabulary, min_shared, and min-graph-size are config calibration knobs
(planner.wagon.*); the GRAPH MATH lives in _wagon_cohesion and is unit-tested.

Convention: src/atdd/planner/conventions/nodes/planner.wagon.separability.convention.yaml
Rule:       planner.wagon.separability
Run:        atdd validate planner
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.planner.validators._wagon_cohesion import build_edges, separable

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.wagon.separability")
_VALIDATOR_ID = "wagon_separability"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"

_DEFAULT_MIN_SHARED = 2
_DEFAULT_MIN_SIZE = 3
# grammar + ubiquitous domain words that would over-connect every WMBT
_STOP = {
    "when", "with", "that", "this", "into", "from", "than", "then", "they", "them",
    "their", "were", "will", "must", "every", "each", "because", "which", "while",
    "where", "what", "does", "not", "and", "for", "the", "via", "per", "without",
    "after", "before", "during", "over", "under", "across", "being", "have", "has",
}


def wmbt_salient_tokens(text: str) -> Set[str]:
    """Salient tokens from object_of_control / statement (calibration knob)."""
    words = re.split(r"[-_\s:.,/()]+", (text or "").lower())
    return {w for w in words if len(w) >= 4 and w not in _STOP}


def _config(repo_root: Path, key: str, default: int) -> int:
    try:
        cfg = yaml.safe_load((repo_root / ".atdd" / "config.yaml").read_text()) or {}
        val = ((cfg.get("planner") or {}).get("wagon") or {}).get(key)
        return int(val) if val is not None else default
    except Exception:
        return default


def load_wmbts_by_wagon(plan_dir: Path) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Return (wmbt_tokens {gid: tokens}, wagon_members {wagon: {gid}}). gid = wagon:id."""
    wmbt_tokens: Dict[str, Set[str]] = {}
    wagon_members: Dict[str, Set[str]] = {}
    for mf in sorted(plan_dir.glob("*/[A-Z]*.yaml")):
        try:
            d = yaml.safe_load(mf.read_text()) or {}
        except Exception:
            continue
        urn = str(d.get("urn", ""))
        if not urn.startswith("wmbt:"):
            continue
        wagon = urn.split(":")[1]
        gid = f"{wagon}:{mf.stem}"
        wmbt_tokens[gid] = wmbt_salient_tokens(
            f"{d.get('object_of_control', '')} {d.get('statement', '')}"
        )
        wagon_members.setdefault(wagon, set()).add(gid)
    return wmbt_tokens, wagon_members


def _scan(
    wmbt_tokens: Dict[str, Set[str]],
    wagon_members: Dict[str, Set[str]],
    min_shared: int,
    min_size: int,
) -> List[Violation]:
    """Emit an advisory [MERGE] for each non-separable wagon (>= min_size WMBTs)."""
    edges = build_edges(wmbt_tokens, min_shared=min_shared)
    violations: List[Violation] = []
    for wagon, members in sorted(wagon_members.items()):
        if len(members) < min_size:
            continue  # min-graph-size guard: too small to assess internal structure
        is_sep, coh, max_coupling, neighbor = separable(wagon, wagon_members, edges)
        if not is_sep:
            wd = wagon.replace("-", "_")
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"plan/{wd}/_{wd}.yaml:1",
                    detail=(
                        f"[MERGE] wagon '{wagon}' cohesion={coh} < coupling={max_coupling} "
                        f"to '{neighbor}' — more bound to a neighbor than to itself"
                    ),
                )
            )
    return violations


def _scan_live() -> List[Violation]:
    wmbt_tokens, wagon_members = load_wmbts_by_wagon(PLAN_DIR)
    return _scan(
        wmbt_tokens,
        wagon_members,
        _config(REPO_ROOT, "separability_min_shared", _DEFAULT_MIN_SHARED),
        _config(REPO_ROOT, "separability_min_graph_size", _DEFAULT_MIN_SIZE),
    )


def test_wagon_separability_reported() -> None:
    """Advisory report of non-separable wagons (non-blocking — advisory disposition)."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


def test_separability_flags_synthetic_merge() -> None:
    """RED guard: a wagon with 0 internal cohesion but cross-coupling is flagged [MERGE]."""
    wmbt_tokens = {
        "w1:A": {"alpha", "p"}, "w1:B": {"alpha", "q"}, "w1:C": {"alpha", "r"},  # cohesive
        "w3:X": {"p", "s"}, "w3:Y": {"q", "t"}, "w3:Z": {"r", "u"},              # 0 internal, coupled to w1
    }
    wagon_members = {
        "w1": {"w1:A", "w1:B", "w1:C"},
        "w3": {"w3:X", "w3:Y", "w3:Z"},
    }
    vios = _scan(wmbt_tokens, wagon_members, min_shared=1, min_size=3)
    merges = [v for v in vios if "w3" in v.location or "w3" in v.detail]
    assert merges and "[MERGE]" in merges[0].detail and "w1" in merges[0].detail, vios
    # the cohesive wagon w1 must NOT itself be flagged (subject, not neighbor)
    assert not [v for v in vios if "wagon 'w1'" in v.detail]
