# URN: component:govern-lifecycle:enforcement-substrate:test_metric_implementation:backend:tests
# Runtime: python
# Purpose: Substrate enforcement (#410) — every signal.metric must have a compute() implementation in either lookup root.

"""Substrate Class 1 conformance: metric implementation existence (spec v12 §7.3).

For every rule with ``signal_metric`` populated in the registry, this
validator checks that AT LEAST ONE of the two lookup roots:

  1. ``<repo>/.atdd/metrics/<metric>.py``        (consumer-authored)
  2. ``src/atdd/runners/metrics/<metric>.py``    (toolkit commons)

(a) exists as a Python module, AND
(b) imports cleanly, AND
(c) exports a callable named ``compute``.

A file that exists but doesn't import — or imports but doesn't define
``compute`` — fires the rule. The metric runner (#412) and this
validator share ``discover_metric_module`` from
``atdd.runners.metric_runner`` so the two are guaranteed to agree on
what counts as "resolvable".

Failures route through ``assert_disposition_satisfied`` under
``tester.acceptance-violation.metric-implementation-must-exist`` (strict).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import RuleMetadata, bind_rule, find_repo_rules
from atdd.coach.validators._violation import Violation
from atdd.runners.metric_runner import discover_metric_module
from atdd.tester.validators._acceptance_walker import assert_substrate_strict


pytestmark = [pytest.mark.platform]


_RULE = bind_rule(
    "tester.acceptance-violation.metric-implementation-must-exist"
)
_VALIDATOR_ID = (
    "test_metric_implementation::test_every_signal_metric_has_compute_function"
)


def _repo_rules_with_signal_metric(
    repo_root: Path,
) -> Iterable[RuleMetadata]:
    """Yield repo-derived RuleMetadata entries with ``signal_metric`` populated.

    Walks ``<repo>/plan/`` via ``find_repo_rules`` (substrate spec §4.2 — issue
    #408). Repo-derived rules are the only ones declaring ``signal.metric``
    in the substrate model; toolkit conventions don't carry it.
    """
    seen: set = set()
    for _src, meta in find_repo_rules(repo_root):
        if not meta.signal_metric:
            continue
        if meta.rule_id in seen:
            continue
        seen.add(meta.rule_id)
        yield meta


def collect_violations(repo_root: Optional[Path] = None) -> List[Violation]:
    """Walk plan/ rules and return missing-metric-implementation violations."""
    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    violations: List[Violation] = []

    for meta in _repo_rules_with_signal_metric(root):
        metric_name = meta.signal_metric or ""
        lookup = discover_metric_module(metric_name, root)
        if lookup.module is not None:
            continue

        repo_candidate = root / ".atdd" / "metrics" / f"{metric_name}.py"
        toolkit_candidate = (
            Path(__file__).resolve().parents[2]
            / "runners"
            / "metrics"
            / f"{metric_name}.py"
        )
        existing: List[str] = []
        if repo_candidate.is_file():
            existing.append(str(repo_candidate))
        if toolkit_candidate.is_file():
            existing.append(str(toolkit_candidate))

        if existing:
            detail = (
                f"signal.metric={metric_name!r} declared by rule "
                f"{meta.rule_id!r} but the candidate file(s) "
                f"{existing} either fail to import or do not export a "
                f"callable 'compute'"
            )
        else:
            detail = (
                f"signal.metric={metric_name!r} declared by rule "
                f"{meta.rule_id!r} but no implementation exists in "
                f"either lookup root: <repo>/.atdd/metrics/"
                f"{metric_name}.py or src/atdd/runners/metrics/"
                f"{metric_name}.py"
            )

        location = (
            str(meta.acceptance_urn)
            if getattr(meta, "acceptance_urn", None)
            else str(meta.source_path)
        )

        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=location,
                detail=detail,
                fix_hint_ref=_RULE.fix_hint_ref,
            )
        )

    return violations


def test_every_signal_metric_has_compute_function() -> None:
    """Every signal.metric in the registry must resolve to a compute() module (§7.3)."""
    violations = collect_violations()
    assert_substrate_strict(_VALIDATOR_ID, violations)


__all__ = [
    "collect_violations",
    "test_every_signal_metric_has_compute_function",
]
