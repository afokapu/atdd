# URN: component:govern-lifecycle:enforcement-substrate:test_hermetic_live_smoke_pairing:backend:application
# Runtime: python
# Purpose: Issue #690 — a hermetic acceptance declaring live_smoke_required: true must have a paired live_smoke sibling under the same WMBT.

"""Hermetic live-smoke pairing conformance validator (issue #690).

Binds
``tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance``.

A fake-backed hermetic acceptance proves request/response shape and sequence
but cannot prove current auth, rate limits, or provider drift. When its author
declares ``hermetic.live_smoke_required: true``, the substrate forces a paired
sibling acceptance with ``execution_kind: live_smoke`` under the SAME parent
WMBT (pairing scope is WMBT-only, Decision #5).

``evaluate_hermetic_live_smoke_pairing`` is a pure evaluator: it accepts a
sequence of ``(path, wmbt_dict)`` pairs (each WMBT dict carrying an
``acceptances`` list) and returns a list of ``Violation`` records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.tester.validators._acceptance_walker import (
    acceptance_urn,
    assert_substrate_strict,
)


pytestmark = [pytest.mark.platform]


_RULE = bind_rule(
    "tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance"
)
_VALIDATOR_ID = (
    "test_hermetic_live_smoke_pairing::test_hermetic_live_smoke_required_is_paired"
)

# WMBT filename grammar — mirrors _acceptance_walker._WMBT_FILE_RE.
import re as _re

_WMBT_FILE_RE = _re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")


def evaluate_hermetic_live_smoke_pairing(
    items: Sequence[Tuple[Path, Dict[str, Any]]],
) -> List[Violation]:
    """Return live-smoke pairing violations for the given WMBT blocks.

    Pure function. ``items`` is a sequence of ``(path, wmbt_dict)`` pairs.
    A Violation is emitted for every acceptance in a WMBT that declares
    ``execution_kind: hermetic_integration`` and ``hermetic.live_smoke_required:
    true`` when that SAME WMBT carries no sibling acceptance with
    ``execution_kind: live_smoke``.
    """
    violations: List[Violation] = []

    for path, wmbt in items:
        if not isinstance(wmbt, dict):
            continue
        acceptances = wmbt.get("acceptances")
        if not isinstance(acceptances, list):
            continue

        wmbt_urn = wmbt.get("urn") or "<no-urn>"
        has_live_smoke_sibling = any(
            isinstance(a, dict) and a.get("execution_kind") == "live_smoke"
            for a in acceptances
        )

        for acc in acceptances:
            if not isinstance(acc, dict):
                continue
            if acc.get("execution_kind") != "hermetic_integration":
                continue
            hermetic = acc.get("hermetic")
            if not isinstance(hermetic, dict):
                continue
            if hermetic.get("live_smoke_required") is not True:
                continue
            if has_live_smoke_sibling:
                continue

            urn = acceptance_urn(acc) or "<no-urn>"
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=str(path),
                    detail=(
                        f"hermetic acceptance {urn!r} declares "
                        f"live_smoke_required: true but parent WMBT {wmbt_urn!r} "
                        f"has no paired sibling acceptance with "
                        f"execution_kind: live_smoke"
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

    return violations


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ WMBT files and return live-smoke pairing violations."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    items: List[Tuple[Path, Dict[str, Any]]] = []

    plan_dir = (root / "plan").resolve()
    if plan_dir.is_dir():
        for wagon_dir in sorted(plan_dir.iterdir()):
            if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
                continue
            for wmbt_file in sorted(wagon_dir.glob("*.yaml")):
                if not _WMBT_FILE_RE.match(wmbt_file.name):
                    continue
                try:
                    data = yaml.safe_load(wmbt_file.read_text(encoding="utf-8"))
                except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow)
                    # Malformed plan/ YAML is policed by the URN-graph validators.
                    continue
                if isinstance(data, dict):
                    items.append((wmbt_file, data))

    return evaluate_hermetic_live_smoke_pairing(items)


def test_hermetic_live_smoke_required_is_paired() -> None:
    """Every live_smoke_required hermetic acceptance has a paired sibling."""
    assert_substrate_strict(_VALIDATOR_ID, collect_violations())


__all__ = [
    "collect_violations",
    "evaluate_hermetic_live_smoke_pairing",
    "test_hermetic_live_smoke_required_is_paired",
]
