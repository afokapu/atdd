# URN: component:govern-lifecycle:enforcement-substrate:metric_runner:backend:domain
# Runtime: python
# Purpose: Iterate registry rules with signal_metric+threshold, dispatch metric compute()/passes(), and route Violations through the disposition gate (spec v12 §4.5).

"""Metric-mode runner (issue #412, substrate spec v12 §4.5).

Iterates every ``RuleMetadata`` carrying both ``signal_metric`` and
``signal_threshold`` and:

1. Looks up the metric implementation via two-root walk:

   * Repo-local first  — ``<repo>/.atdd/metrics/<name>.py::compute``
   * Toolkit fallback  — ``atdd/runners/metrics/<name>.py::compute``

2. Calls ``compute(repo_root) -> int | float | bool``.
3. Calls ``passes(value, threshold) -> bool`` from the same module.
4. On ``passes() == False`` constructs a ``Violation`` with
   ``rule_id`` = the registry's rule_id and ``location`` = ``"codebase"``.

All violations across all rules are routed through a SINGLE
``assert_disposition_satisfied`` call with
``validator_id="test_metric_runner::test_metric_threshold_satisfied"``.
The gate already groups violations by ``rule_id`` and emits one failure
block per failing rule (verified against ``disposition_gate.py:169-216``
at issue-authoring time).

Skip rules:

* ``signal_metric`` cannot be resolved in either lookup root → SILENTLY
  SKIPPED. The conformance rule
  ``tester.acceptance-violation.metric-implementation-must-exist`` (#410)
  catches missing implementations at validation time; emitting a runtime
  violation here would double-fail the same site.
* ``signal_metric`` populated but ``signal_threshold is None`` (or vice
  versa) → SILENTLY SKIPPED. The
  ``tester.acceptance-violation.acceptance-must-be-measurable`` validator
  (#410) catches the schema violation; runner does not double-emit.

The metric module owns the ``passes`` semantic. The runner does NOT
infer threshold direction from the metric name; supplying a default
``passes`` would silently invert minimum-requirement metrics. See spec
§4.5 lines 252-261.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Sequence

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_id_registry import RuleMetadata, build_registry
from atdd.coach.validators._violation import Violation


_logger = logging.getLogger(__name__)


VALIDATOR_ID = "test_metric_runner::test_metric_threshold_satisfied"
"""Stable validator_id for every metric-runner gate call (spec §4.2)."""


_TOOLKIT_METRICS_PKG = Path(__file__).resolve().parent / "metrics"
"""Filesystem root of toolkit-shipped metric commons."""


def _repo_metrics_root(repo_root: Path) -> Path:
    return repo_root / ".atdd" / "metrics"


def _toolkit_metrics_root() -> Path:
    return _TOOLKIT_METRICS_PKG


@dataclass(frozen=True)
class MetricLookup:
    """Resolution result for one ``signal_metric`` name.

    Attributes:
        name: The metric name as declared on the rule.
        path: Absolute path to the metric module (``<name>.py``), or
            ``None`` if neither root carries it.
        module: Loaded Python module exposing ``compute`` and (optionally)
            ``passes``. ``None`` when ``path is None`` or the module
            failed to import / lacks ``compute``.
        source: ``"repo"``, ``"toolkit"``, or ``None``.
    """

    name: str
    path: Optional[Path]
    module: Optional[ModuleType]
    source: Optional[str]


def discover_metric_module(
    name: str,
    repo_root: Path,
    *,
    toolkit_root: Optional[Path] = None,
) -> MetricLookup:
    """Resolve ``<name>`` against the two-root metric registry.

    Repo-local ``<repo>/.atdd/metrics/<name>.py`` wins on collision. Falls
    back to ``<toolkit_root>/<name>.py``. The module is imported and
    cached at the module-spec level via ``importlib.util.spec_from_file_location``
    so two consumers with different ``foo.py`` files don't shadow each
    other through ``sys.modules``.
    """
    toolkit = toolkit_root if toolkit_root is not None else _toolkit_metrics_root()

    candidates: List[tuple[str, Path]] = [
        ("repo", _repo_metrics_root(repo_root) / f"{name}.py"),
        ("toolkit", toolkit / f"{name}.py"),
    ]

    for source, candidate in candidates:
        if not candidate.is_file():
            continue
        module = _load_module_from_path(candidate)
        if module is None:
            continue
        if not callable(getattr(module, "compute", None)):
            # Module exists but doesn't satisfy the contract; treat as
            # absent so the conformance rule (#410) can flag it. The
            # runner deliberately does not double-emit.
            continue
        return MetricLookup(name=name, path=candidate, module=module, source=source)

    return MetricLookup(name=name, path=None, module=None, source=None)


def _load_module_from_path(path: Path) -> Optional[ModuleType]:
    """Import ``path`` as an isolated module by file location."""
    try:
        unique_name = f"_atdd_metric_{path.parent.name}_{path.stem}_{abs(hash(str(path.resolve())))}"
        spec = importlib.util.spec_from_file_location(unique_name, str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Import-time errors in a metric module are policed by the #410
        # conformance rule (validation-time). The runner skips so it
        # doesn't double-fail; the warning is for operator visibility.
        _logger.warning(
            "metric_runner: failed to import %s: %s",
            path, exc,
            extra={"metric_path": str(path), "error_type": type(exc).__name__},
        )
        return None


def _select_runnable_rules(
    registry: Dict[str, RuleMetadata],
) -> List[RuleMetadata]:
    """Return rules with BOTH ``signal_metric`` and ``signal_threshold`` set.

    Rules with one but not the other are silently skipped — the
    measurability validator (#410) policies the schema violation.
    """
    runnable: List[RuleMetadata] = []
    for meta in registry.values():
        if not isinstance(meta, RuleMetadata):
            continue
        if not meta.signal_metric:
            continue
        if meta.signal_threshold is None:
            continue
        runnable.append(meta)
    return runnable


def _format_metric_detail(metric: str, value: Any, threshold: Any) -> str:
    """Spec §6 sample: ``<metric>=<value>, threshold=<threshold>``."""
    return f"{metric}={value!r}, threshold={threshold!r}"


def _build_violation(
    meta: RuleMetadata,
    value: Any,
    threshold: Any,
) -> Optional[Violation]:
    """Construct the ``Violation`` record for a failing rule.

    Returns ``None`` when severity is missing/non-int — those rules are
    malformed and policed elsewhere; the runner skips defensively.
    """
    severity = meta.severity
    if not isinstance(severity, int) or isinstance(severity, bool):
        _logger.debug(
            "metric_runner: skipping rule %s with non-int severity %r",
            meta.rule_id, severity,
            extra={"rule_id": meta.rule_id, "severity": repr(severity)},
        )
        return None
    if not (1 <= severity <= 5):
        return None
    return Violation(
        rule_id=meta.rule_id,
        severity=severity,
        location="codebase",
        detail=_format_metric_detail(
            meta.signal_metric or "", value, threshold,
        ),
    )


def collect_metric_violations(
    registry: Dict[str, RuleMetadata],
    repo_root: Path,
    *,
    toolkit_root: Optional[Path] = None,
) -> List[Violation]:
    """Pure function: walk the registry and collect failing-rule violations.

    Separated from the gate-emission step so unit tests can inspect the
    list directly without needing pytest.fail interception.
    """
    violations: List[Violation] = []
    seen_ids: set = set()  # canonical ids may appear under both their id and aliases
    for meta in _select_runnable_rules(registry):
        if meta.rule_id in seen_ids:
            continue
        seen_ids.add(meta.rule_id)

        lookup = discover_metric_module(
            meta.signal_metric or "",
            repo_root,
            toolkit_root=toolkit_root,
        )
        if lookup.module is None:
            # Missing implementation → silently skipped (rationale above).
            continue

        passes_fn = getattr(lookup.module, "passes", None)
        if not callable(passes_fn):
            # Module is missing `passes`. Same rationale as missing compute:
            # the #410 conformance rule catches it; runtime does not double-emit.
            continue

        try:
            value = lookup.module.compute(repo_root)
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            _logger.warning(
                "metric_runner: compute() raised for %s: %s",
                meta.signal_metric, exc,
                extra={
                    "metric": meta.signal_metric,
                    "error_type": type(exc).__name__,
                },
            )
            continue

        try:
            ok = passes_fn(value, meta.signal_threshold)
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            _logger.warning(
                "metric_runner: passes() raised for %s: %s",
                meta.signal_metric, exc,
                extra={
                    "metric": meta.signal_metric,
                    "error_type": type(exc).__name__,
                },
            )
            continue

        if ok:
            continue

        violation = _build_violation(meta, value, meta.signal_threshold)
        if violation is not None:
            violations.append(violation)

    return violations


def run_metric_runner(
    *,
    registry: Optional[Dict[str, RuleMetadata]] = None,
    repo_root: Optional[Path] = None,
    toolkit_root: Optional[Path] = None,
) -> None:
    """Run the metric runner and route every failure through the gate.

    Single ``assert_disposition_satisfied`` call: the gate groups by
    ``rule_id`` internally and emits one failure block per failing rule
    (per spec §4.5 and verified against ``disposition_gate.py``). All
    failures surface as ONE pytest failure, with one block per rule.
    """
    reg = registry if registry is not None else build_registry()
    root = repo_root if repo_root is not None else find_repo_root()

    violations = collect_metric_violations(reg, root, toolkit_root=toolkit_root)
    assert_disposition_satisfied(
        validator_id=VALIDATOR_ID,
        violations=violations,
        registry=reg,
        repo_root=root,
    )


__all__ = [
    "VALIDATOR_ID",
    "MetricLookup",
    "collect_metric_violations",
    "discover_metric_module",
    "run_metric_runner",
]
