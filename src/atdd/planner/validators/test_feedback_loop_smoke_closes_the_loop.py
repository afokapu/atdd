# Acceptance: acc:observe-and-correct:P001-SMOKE-002-close-the-loop-smoke-acceptance
# WMBT: wmbt:observe-and-correct:P001
# Phase: SMOKE
# Layer: backend.integration
"""planner.smoke.feedback-loop-close-the-loop validator (issue #825).

Walks every feature YAML under ``plan/<wagon>/features/`` that declares
``kind: feedback-loop``. For each such feature, inspects its WMBT files
to verify at least one SMOKE acceptance declares a ``close_the_loop:``
block with both ``consumer_reacted`` and ``drift_resolved`` sub-fields.

Motivation: the 2026-05-21 incident — feature:observe-and-correct:observer-
runtime-and-rules shipped with 4 SMOKE tests all green while 0 corrections
reached any worker. Every smoke asserted "producer wrote the artifact" but
none asserted "consumer received it." This validator prevents recurrence by
enforcing the close-the-loop assertion pair on every feedback-loop feature.

Convention: ``src/atdd/tester/conventions/smoke.convention.yaml::feedback_loop``
Rule:       ``planner.smoke.feedback-loop-close-the-loop``
Run:        ``atdd validate planner``
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner]


_RULE = bind_rule("planner.smoke.feedback-loop-close-the-loop")
_VALIDATOR_ID = "feedback_loop_smoke_closes_the_loop"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"

# Inline suppression marker on the kind: line of a feature YAML.
_SUPPRESS_RE = re.compile(
    r"atdd:suppress\(planner\.smoke\.feedback-loop-close-the-loop\)"
    r"\s+UNTIL=(\d{4}-\d{2}-\d{2})"
)

# WMBT filename pattern — same set as the wmbt_has_smoke_acceptance validator.
_WMBT_FILENAME_RE = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")

# Acceptance URN with SMOKE token.
_SMOKE_URN_RE = re.compile(
    r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$"
)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def iter_feedback_loop_features(
    plan_dir: Path,
) -> List[Tuple[Path, Dict[str, Any]]]:
    """Walk plan_dir and return (path, data) for features with kind: feedback-loop."""
    if not plan_dir.exists():
        return []
    results: List[Tuple[Path, Dict[str, Any]]] = []
    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        features_dir = wagon_dir / "features"
        if not features_dir.is_dir():
            continue
        for yaml_file in sorted(features_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as fh:
                    data = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                continue
            if not isinstance(data, dict):
                continue
            if data.get("kind") == "feedback-loop":
                results.append((yaml_file, data))
    return results


def _wmbt_urn_to_path(plan_dir: Path, wmbt_urn: str) -> Optional[Path]:
    """Resolve wmbt:<wagon>:<ID> to plan/<wagon_snake>/<ID>.yaml."""
    parts = wmbt_urn.split(":")
    if len(parts) != 3 or parts[0] != "wmbt":
        return None
    wagon_slug = parts[1].replace("-", "_")
    wmbt_id = parts[2]
    candidate = plan_dir / wagon_slug / f"{wmbt_id}.yaml"
    return candidate if candidate.exists() else None


def load_wmbt_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load a WMBT YAML file; return None on error."""
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def acceptance_has_close_the_loop(acc: Any) -> bool:
    """True if the acceptance declares a close_the_loop block with both sub-fields."""
    if not isinstance(acc, dict):
        return False
    ctl = acc.get("close_the_loop")
    if not isinstance(ctl, dict):
        return False
    consumer_reacted = ctl.get("consumer_reacted")
    drift_resolved = ctl.get("drift_resolved")
    return bool(consumer_reacted) and bool(drift_resolved)


def wmbt_has_close_the_loop_smoke(wmbt_data: Dict[str, Any]) -> bool:
    """True if the WMBT has at least one SMOKE acceptance with a close_the_loop block."""
    acceptances = wmbt_data.get("acceptances") or []
    for acc in acceptances:
        if not isinstance(acc, dict):
            continue
        identity = acc.get("identity") or {}
        phase = identity.get("phase", "")
        urn = identity.get("urn", "")
        is_smoke = phase == "SMOKE" or bool(_SMOKE_URN_RE.match(urn))
        if is_smoke and acceptance_has_close_the_loop(acc):
            return True
    return False


def _find_kind_lineno(feature_path: Path) -> int:
    """Return 1-based line number of the kind: field (for suppress-marker scanning)."""
    try:
        with open(feature_path) as fh:
            for idx, line in enumerate(fh, start=1):
                if line.lstrip().startswith("kind:"):
                    return idx
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pass
    return 1


def _is_suppressed(feature_path: Path, lineno: int) -> bool:
    """Check if the kind: line has an inline suppression marker."""
    try:
        with open(feature_path) as fh:
            lines = fh.readlines()
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        return bool(_SUPPRESS_RE.search(line))
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return False


# ---------------------------------------------------------------------------
# Pure evaluator
# ---------------------------------------------------------------------------


def evaluate_feedback_loop_coverage(
    feature_files: Sequence[Tuple[Path, Dict[str, Any]]],
    plan_dir: Path,
    repo_root: Path,
) -> List[Violation]:
    """Emit one Violation per feedback-loop feature lacking a close-the-loop SMOKE."""
    violations: List[Violation] = []
    for feature_path, feature_data in feature_files:
        lineno = _find_kind_lineno(feature_path)
        if _is_suppressed(feature_path, lineno):
            continue

        wmbt_urns: List[str] = feature_data.get("wmbts") or []
        found_close_the_loop = False
        for wmbt_urn in wmbt_urns:
            if not isinstance(wmbt_urn, str):
                continue
            wmbt_path = _wmbt_urn_to_path(plan_dir, wmbt_urn)
            if wmbt_path is None:
                continue
            wmbt_data = load_wmbt_yaml(wmbt_path)
            if wmbt_data is None:
                continue
            if wmbt_has_close_the_loop_smoke(wmbt_data):
                found_close_the_loop = True
                break

        if found_close_the_loop:
            continue

        feature_urn = feature_data.get("urn", "")
        try:
            rel = feature_path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = feature_path.as_posix()

        detail = (
            f"Feature {feature_urn or feature_path.stem!r} is marked "
            f"`kind: feedback-loop` but none of its {len(wmbt_urns)} WMBT(s) "
            f"declare a SMOKE acceptance with a `close_the_loop:` block "
            f"(consumer_reacted + drift_resolved). Producer-only SMOKE assertions "
            f"are insufficient — they allow the consumer end of the loop to be "
            f"completely unwired while CI stays green. Add a close_the_loop: block "
            f"to a SMOKE acceptance on the primary WMBT for this feature."
        )
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{rel}:{lineno}",
                detail=detail,
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
    return violations


def scan_plan_for_feedback_loop_coverage(
    plan_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: load feedback-loop features, emit Violations."""
    root = repo_root or REPO_ROOT
    pdir = plan_dir or (root / "plan")
    features = iter_feedback_loop_features(pdir)
    return evaluate_feedback_loop_coverage(features, pdir, root)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_every_feedback_loop_feature_has_close_the_loop_smoke():
    """
    SPEC: ``smoke.convention.yaml::feedback_loop_rules[planner.smoke.feedback-loop-close-the-loop]``.

    Given: Every feature YAML under ``plan/<wagon>/features/`` with ``kind: feedback-loop``.
    When:  Inspecting the feature's WMBTs for a SMOKE acceptance with a
           ``close_the_loop:`` block containing ``consumer_reacted`` and
           ``drift_resolved``.
    Then:  At least one such acceptance exists. Features lacking it surface as
           structured Violations the disposition gate fails on (unless the kind:
           line is inline-suppressed).
    """
    violations = scan_plan_for_feedback_loop_coverage()
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )
