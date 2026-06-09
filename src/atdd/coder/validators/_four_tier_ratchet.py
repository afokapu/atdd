# URN: component:govern-lifecycle:config-driven-four-tier-validators:four_tier_ratchet:backend:application
# Runtime: python
# Purpose: Grandfather today's toolkit four-tier debt so config-driving fails only on NEW violations (#958).

"""Ratchet baseline for the config-driven four-tier toolkit checks (#958, Part B).

Honoring ``code.toolkit`` makes the composition-completeness validator see the
toolkit's full pre-four-tier debt at once. A naive landing would turn
``validate-coder`` red on dozens of untouched legacy files — an unmergeable wall.

The ratchet snapshots today's toolkit violations into a frozen, grandfathered
baseline (``.atdd/baselines/four_tier_toolkit.yaml``). The gate then fails only on
NEW or growing violations: a touched legacy file must not ADD a violation, but no
untouched legacy file may start failing. The debt is frozen, visible (logged),
and shrinking — never rewritten in one shot (strangler-fig at the process level).

This mirrors the #482 suppress-and-clean disposition: a baseline entry is the
"grandfathered" marker. The baseline is a SET of stable violation identities
(``rule_id::location``) rather than inline source markers, because composition
violations are keyed by ``feature_id/file`` not a literal source line.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Set

import yaml

from atdd.coach.validators._violation import Violation
from atdd.coder.validators._toolkit_roots import resolve_scan_roots
from atdd.coder.validators.test_composition_completeness import analyze_python_root

logger = logging.getLogger(__name__)

# Baseline relative to repo root. Reuses the .atdd/baselines/ home (#482).
BASELINE_REL = Path(".atdd/baselines/four_tier_toolkit.yaml")


def violation_identity(violation: Violation) -> str:
    """Stable identity for a violation: ``rule_id::location``.

    Composition locations are ``feature_id/file`` (repo-relative and rename-stable
    within a feature), so the identity survives unrelated edits elsewhere.
    """
    return f"{violation.rule_id}::{violation.location}"


def collect_toolkit_violations(
    repo_root: Path, config: Optional[Mapping[str, Any]]
) -> List[Violation]:
    """Collect four-tier composition violations across the toolkit scan roots.

    Only roots carrying a package ``import_prefix`` (i.e. the ``code.toolkit``
    root, not the consumer ``python/`` tree) are analyzed — the consumer tree is
    already gated by the existing live composition tests.
    """
    violations: List[Violation] = []
    for scan_root in resolve_scan_roots(config, repo_root):
        if not scan_root.import_prefix:
            continue
        violations.extend(analyze_python_root(repo_root, scan_root))
    return violations


def load_grandfathered_baseline(repo_root: Path) -> Set[str]:
    """Load the set of grandfathered violation identities (empty when absent)."""
    path = repo_root / BASELINE_REL
    if not path.exists():
        return set()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        logger.warning("could not read four-tier baseline", extra={"path": str(path)})
        return set()
    grandfathered = data.get("grandfathered") or []
    return {str(item) for item in grandfathered}


def new_violations(
    violations: Sequence[Violation], baseline: Set[str]
) -> List[Violation]:
    """Return only the violations whose identity is NOT grandfathered."""
    return [v for v in violations if violation_identity(v) not in baseline]


def write_grandfathered_baseline(
    repo_root: Path, violations: Sequence[Violation]
) -> Path:
    """Snapshot *violations* into the grandfathered baseline file.

    Returns the path written. Identities are sorted for a deterministic diff.
    """
    identities = sorted({violation_identity(v) for v in violations})
    path = repo_root / BASELINE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "validator": "four_tier_toolkit_composition",
        "note": (
            "Grandfathered toolkit four-tier composition debt (#958). The gate "
            "fails only on violations NOT listed here. Shrink this list; never "
            "grow it. Regenerate intentionally, never to absorb a new regression."
        ),
        "grandfathered": identities,
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def assert_ratchet_satisfied(
    repo_root: Path, config: Optional[Mapping[str, Any]]
) -> List[Violation]:
    """Gate the toolkit four-tier debt against the grandfathered baseline.

    Logs what is grandfathered (the debt is never silently covered — #958) and
    returns the list of NEW violations. Callers fail the gate when it is non-empty.
    """
    violations = collect_toolkit_violations(repo_root, config)
    baseline = load_grandfathered_baseline(repo_root)
    leaked = new_violations(violations, baseline)
    logger.info(
        "four-tier toolkit ratchet",
        extra={
            "grandfathered": len(baseline),
            "current": len(violations),
            "new": len(leaked),
        },
    )
    return leaked
