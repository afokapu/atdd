#!/usr/bin/env python3
"""#1972 lab — is a toolkit-resident module per metric id implementable at all?

Read-only. Run from the repo root: `python3 docs/spikes/labs/1972-metric-id-is-a-category/corpus_ratio.py`

#1972 proposes implementing the ten metric ids that
`planner.criteria.metric-mapping` names, as modules under
`src/atdd/runners/metrics/<id>.py`, each exporting `compute` + `passes`.

The runner's contract is the constraint (`runners/metric_runner.py:328`):

    value = lookup.module.compute(repo_root)

ONE argument. A metric module is told which REPOSITORY to measure and never
which SUBJECT within it. `hardcoded_theme_map_literal_count` satisfies that
because its name fixes the quantity: "hardcoded theme_map literals under
src/atdd/". The ten mapped ids do not — they are dimension defaults
(likelihood/minimize -> metric:error_ratio), and "the error ratio" is not a
quantity until something says the error ratio OF WHAT.

Each WMBT answers that question in its own `object_of_control` field. This
script measures the ratio that decides the issue:

    WMBTs inheriting a metric id   vs   distinct object_of_control among them

If the ratio is ~1:1, one module per id cannot serve them: a single
`compute(repo_root)` would have to return one number that judges every
distinct subject that inherited the id.
"""
from __future__ import annotations

import collections
import pathlib
import sys

import yaml

DOWNWARD = {"minimize", "decrease"}
UPWARD = {"maximize", "increase"}

# planner.criteria.metric-mapping, term_id: dimension_metric.
# Keyed (dimension, is_upward) since #1959 resolved both spellings of an intent
# to one metric id.
MAPPING = {
    ("time", 0): "latency_p50",          ("time", 1): "latency_increase",
    ("effort", 0): "user_steps",         ("effort", 1): "unmapped",
    ("likelihood", 0): "error_ratio",    ("likelihood", 1): "success_ratio",
    ("frequency", 0): "occurrence_rate", ("frequency", 1): "unmapped",
    ("quantity", 0): "scrap_rate",       ("quantity", 1): "throughput",
    ("financial value", 0): "cost_per_unit", ("financial value", 1): "net_margin",
}


def main(root: pathlib.Path) -> int:
    counts: collections.Counter = collections.Counter()
    subjects: dict[str, set] = collections.defaultdict(set)
    wmbts = bars = unresolved = 0

    for path in (root / "plan").rglob("*.yaml"):
        try:
            doc = yaml.safe_load(path.read_text())
        except Exception:
            continue
        if not isinstance(doc, dict) or "dimension" not in doc or "direction" not in doc:
            continue
        wmbts += 1
        dimension = str(doc["dimension"]).strip()
        direction = str(doc["direction"]).strip()
        if direction in UPWARD:
            upward = 1
        elif direction in DOWNWARD:
            upward = 0
        else:
            unresolved += 1
            continue
        metric_id = MAPPING.get((dimension, upward))
        if metric_id is None:
            unresolved += 1
            continue
        counts[metric_id] += 1
        subjects[metric_id].add(str(doc.get("object_of_control", "?")))
        for acc in doc.get("acceptances") or []:
            signal = acc.get("signal") if isinstance(acc, dict) else None
            if isinstance(signal, dict) and signal.get("metric"):
                bars += 1

    print(f"WMBT files:                          {wmbts}")
    print(f"acceptances stating an executable bar: {bars}")
    print(f"dimension+direction unresolved:        {unresolved}\n")

    print(f"{'metric id':<18}{'WMBTs':>7}{'distinct subjects':>20}{'ratio':>9}")
    print("-" * 54)
    for metric_id, n in counts.most_common():
        distinct = len(subjects[metric_id])
        print(f"{metric_id:<18}{n:>7}{distinct:>20}{distinct / n:>9.2f}")

    mapped = sum(n for mid, n in counts.items() if mid != "unmapped")
    distinct_total = len(set().union(*(s for mid, s in subjects.items() if mid != "unmapped")))
    print("-" * 54)
    print(f"{'TOTAL mapped':<18}{mapped:>7}{distinct_total:>20}"
          f"{distinct_total / mapped:>9.2f}")

    print("\nVERDICT")
    if distinct_total / mapped > 0.9:
        print(f"  {mapped} WMBTs inherit a metric id and name {distinct_total} distinct")
        print("  subjects — effectively one subject each. A toolkit module per id would")
        print("  have to return ONE number per repository that judges all of them.")
        print("  The ten ids are metric CATEGORIES, not metrics. Not implementable")
        print("  under compute(repo_root).")
    else:
        print("  Subjects cluster; a shared implementation per id may be possible.")
    return 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
