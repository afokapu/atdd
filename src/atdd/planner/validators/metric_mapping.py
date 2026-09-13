# Component: component:define-plans:criteria:MetricMapping:backend:domain
"""Dimension->metric coverage across the authored corpus (#1958).

`planner.criteria.metric-mapping` declares that every WMBT dimension+direction
has a default metric — `likelihood/minimize` is an error ratio,
`likelihood/maximize` a success ratio, `frequency/decrease` an occurrence rate.
It declared that and bound nothing: no `implementation:`, no `validation:`, and
`metric_id` appeared in no schema and no validator. If the toolkit is willing to
say a dimension MEANS a rate, it has already asserted the outcome is a rate, and
a rate is only an acceptance once it has a bar.

This is the corpus half: a pure scanner over WMBT dicts, plus the walk that
collects them. It reports; it never blocks — the disposition lives on the
convention node and is advisory, because all 368 covered WMBTs state no bar and
the remedy is not yet affordable (no `error_ratio`, `success_ratio` or
`occurrence_rate` module exists for the metric runner to resolve).

The mapping is READ FROM THE NODE rather than restated here. A second copy is
how the node drifts back into describing something nothing checks, which is the
defect this module exists to close. #1943 made the same move for the verb
lexicon.

The scanner takes PARSED WMBT DICTS, not paths, so the judgement is testable
without a filesystem and the walk is a separate, trivially-checkable concern.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

__all__ = [
    "CAUSE_NO_BAR",
    "CAUSE_OFF_MAP",
    "Unmeasured",
    "corpus_wmbts",
    "dimension_metric_map",
    "scan_corpus",
    "scan_wmbts",
]

#: Causes are kept apart because their REMEDIES differ. A WMBT with no bar is
#: missing a threshold and gets one authored. A WMBT whose bar names a metric
#: the mapping does not assign means either the acceptance or the mapping is
#: wrong — a judgement call, not a fill-in. Collapsing them into one count would
#: hide that distinction and make the report a number.
CAUSE_NO_BAR = "no-executable-bar"
CAUSE_OFF_MAP = "bar-off-map"

#: The value the convention writes for a legal dimension+direction pair that has
#: no default metric. Present only since #1959 made the table total; before that
#: such a pair was simply missing from the table.
UNMAPPED_SENTINEL = "unmapped"

_NODE = (
    Path(__file__).resolve().parents[1]
    / "conventions"
    / "nodes"
    / "planner.criteria.metric-mapping.convention.yaml"
)
_TERM_ID = "dimension_metric"


@dataclass(frozen=True)
class Unmeasured:
    """One WMBT the mapping covers that does not state the bar it implies."""

    wmbt_urn: str
    dimension: str
    direction: str
    metric_id: str   # what the convention assigns this dimension+direction
    cause: str       # CAUSE_NO_BAR | CAUSE_OFF_MAP
    detail: str


def _canonical_dimension(label: str) -> str:
    """Reconcile a node dimension label with the `wmbt.schema.json` enum.

    The node writes `quantity / amount`; the schema enum says `quantity`. Left
    unreconciled, the 10 real `quantity/maximize` WMBTs the convention DOES map
    would read as unmapped and the mapping would under-claim its own coverage.
    Only the alias form is normalised — no dimension is invented.
    """
    return label.split("/", 1)[0].strip()


def _mapping_values(data: Dict) -> Dict:
    """The `values` block of the dimension->metric term, or an empty dict."""
    for term in data.get("terms") or []:
        if isinstance(term, dict) and term.get("term_id") == _TERM_ID:
            return term.get("values") or {}
    return {}


def dimension_metric_map(node_path: Optional[Path] = None) -> Dict[Tuple[str, str], str]:
    """Read `(dimension, direction) -> metric_id` from the convention node itself.

    Pairs carrying ``UNMAPPED_SENTINEL`` are omitted. #1959 made the table TOTAL
    over the dimension x direction enums, so a pair with no default metric is now
    PRESENT and carries the sentinel rather than being absent. Absent and
    explicitly-unmapped mean the same thing here — there is no metric to demand a
    bar for — and the sentinel must not be mistaken for a metric_id, which is what
    a bare truthiness check on the looked-up value would do.
    """
    path = Path(node_path) if node_path else _NODE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    return {
        (_canonical_dimension(str(dimension)), str(direction)): str(metric_id)
        for dimension, directions in _mapping_values(data).items()
        if isinstance(directions, dict)
        for direction, metric_id in directions.items()
        if str(metric_id) != UNMAPPED_SENTINEL
    }


def _bar_metrics(wmbt: Dict) -> List[str]:
    """Every metric named by an acceptance that states an executable bar.

    `threshold` is checked against ``None``, never for truthiness: `0` and
    `false` are meaningful thresholds, and the one WMBT in the corpus that
    states a bar uses `0`.
    """
    metrics: List[str] = []
    for acceptance in wmbt.get("acceptances") or []:
        if not isinstance(acceptance, dict):
            continue
        signal = acceptance.get("signal")
        if not isinstance(signal, dict):
            continue
        metric = signal.get("metric")
        if metric and signal.get("threshold") is not None:
            metrics.append(str(metric))
    return metrics


def _bare(metric: str) -> str:
    """Compare metric names without the `metric:` prefix.

    The mapping writes `metric:error_ratio`; a real acceptance writes the module
    name the metric runner resolves (`hardcoded_theme_map_literal_count`). The
    prefix is a namespace, not part of the identity.
    """
    return metric.split(":", 1)[1] if metric.startswith("metric:") else metric


def scan_wmbts(
    wmbts: Iterable[Dict],
    mapping: Optional[Dict[Tuple[str, str], str]] = None,
) -> List[Unmeasured]:
    """Report each WMBT the mapping covers that does not state the bar it implies.

    A WMBT whose dimension+direction the convention does NOT map is never
    reported: the convention assigns it no metric, so there is no bar for it to
    owe, and reporting it would invent an obligation the convention never made.
    """
    table = dimension_metric_map() if mapping is None else mapping
    findings: List[Unmeasured] = []

    for wmbt in wmbts:
        dimension = str(wmbt.get("dimension") or "")
        direction = str(wmbt.get("direction") or "")
        metric_id = table.get((dimension, direction))
        if not metric_id:
            continue

        urn = str(wmbt.get("urn") or "")
        metrics = _bar_metrics(wmbt)
        if not metrics:
            findings.append(Unmeasured(
                urn, dimension, direction, metric_id, CAUSE_NO_BAR,
                "no acceptance states signal.metric with a signal.threshold",
            ))
        elif not any(_bare(m) == _bare(metric_id) for m in metrics):
            findings.append(Unmeasured(
                urn, dimension, direction, metric_id, CAUSE_OFF_MAP,
                f"the stated bar names {', '.join(sorted(metrics))}",
            ))
    return findings


def corpus_wmbts(plan_root: Path) -> List[Dict]:
    """Every WMBT authored under *plan_root*."""
    wmbts: List[Dict] = []
    for path in sorted(Path(plan_root).rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            # Narrow, and logged with the path: one malformed file must not
            # hide the coverage gap in every good one.
            logger.warning(
                "metric-mapping corpus scan skipped an unreadable plan file",
                extra={"path": str(path), "error": str(exc)},
            )
            continue
        if isinstance(data, dict) and str(data.get("urn", "")).startswith("wmbt:"):
            wmbts.append(data)
    return wmbts


def scan_corpus(plan_root: Path) -> List[Unmeasured]:
    """Scan every WMBT under *plan_root* against the node's mapping."""
    return scan_wmbts(corpus_wmbts(plan_root))
