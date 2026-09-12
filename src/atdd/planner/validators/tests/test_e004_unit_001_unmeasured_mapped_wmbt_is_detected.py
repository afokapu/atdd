# URN: test:define-plans:atdd-plan-session:E004-UNIT-001-unmeasured-mapped-wmbt-is-detected
# Acceptance: acc:define-plans:E004-UNIT-001-unmeasured-mapped-wmbt-is-detected
# WMBT: wmbt:define-plans:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-001 — a WMBT the mapping covers but states no bar is detected (#1958).

`planner.criteria.metric-mapping` says every WMBT dimension+direction has a
default metric: `likelihood/minimize` is an error ratio, `likelihood/maximize` a
success ratio. It carried no `implementation:` and no `validation:`, so nothing
read it and `metric_id` was a term no schema knew. Measured over the corpus, 368
of 472 WMBTs have a dimension+direction the convention maps, and none of them
states an executable bar — the one WMBT that does is `quantity/minimize`, which
the mapping does not cover.

This is the unit contract for the scanner that closes that gap. Two assertions
carry the design.

The first is the cause split. A mapped WMBT with NO bar and a mapped WMBT whose
bar names some OTHER metric are different findings with different remedies: the
first is missing a threshold, the second means either the acceptance or the
mapping is wrong, and collapsing them into one count would hide the distinction.

The second is that the mapping is read from the convention node rather than
restated here. #1943 made the same move for the verb lexicon: if the scanner
keeps its own copy, the node and its validator can drift into disagreeing about
what a dimension means, and the node goes back to describing something nothing
checks — the exact defect this issue exists to fix.

The scanner reports; it never blocks. Its disposition is advisory because all
368 would fail on day one, and a rule with no affordable remedy is one that gets
ignored.
"""
from __future__ import annotations

import pytest

from atdd.planner.validators.metric_mapping import (
    CAUSE_NO_BAR,
    CAUSE_OFF_MAP,
    dimension_metric_map,
    scan_wmbts,
)

pytestmark = [pytest.mark.planner]


def _wmbt(code: str, dimension: str, direction: str, signal: dict | None = None) -> dict:
    """A WMBT dict in the shape the plan/ files carry."""
    acceptance: dict = {
        "identity": {"urn": f"acc:demo:{code}-UNIT-001-x", "id": "AC-UNIT-001", "phase": "GREEN"},
        "harness": {"type": "unit"},
    }
    if signal is not None:
        acceptance["signal"] = signal
    return {
        "urn": f"wmbt:demo:{code}",
        "dimension": dimension,
        "direction": direction,
        "acceptances": [acceptance],
    }


def test_a_mapped_wmbt_with_no_bar_is_reported_with_the_metric_it_owes():
    findings = scan_wmbts([_wmbt("E001", "likelihood", "minimize")])

    assert len(findings) == 1
    assert findings[0].wmbt_urn == "wmbt:demo:E001"
    assert findings[0].cause == CAUSE_NO_BAR
    assert findings[0].metric_id == "metric:error_ratio"


def test_an_unmapped_wmbt_is_not_reported():
    """The convention assigns it no metric, so there is no bar for it to owe.

    Reporting such a WMBT would be the scanner inventing an obligation the
    convention never stated.

    The example is `effort/maximize`, which carries the `unmapped` sentinel.
    This test used `quantity/minimize` until #1959 made the table total over
    the dimension x direction enums and mapped that pair to `metric:scrap_rate`
    — it had only ever been unmapped because the table spelled the direction
    `decrease`. A pair that is unmapped by intent, rather than by a spelling
    gap, is the thing this test is actually about.
    """
    assert scan_wmbts([_wmbt("E002", "effort", "maximize")]) == []


def test_the_unmapped_sentinel_is_not_mistaken_for_a_metric(tmp_path):
    """`unmapped` is an absence, not a metric_id (#1959 + #1958 interaction).

    Since the table became total, a pair with no default metric is PRESENT and
    carries the sentinel rather than being missing. A truthiness check on the
    looked-up value would read `"unmapped"` as a real metric and demand a bar
    naming it.
    """
    from atdd.planner.validators.metric_mapping import dimension_metric_map

    table = dimension_metric_map()
    assert ("effort", "maximize") not in table
    assert "unmapped" not in set(table.values())
    # ...and the mapped pairs are still there.
    assert table[("likelihood", "minimize")] == "metric:error_ratio"
    assert table[("quantity", "minimize")] == "metric:scrap_rate"


def test_a_conforming_wmbt_is_not_reported():
    findings = scan_wmbts([
        _wmbt("E003", "likelihood", "minimize",
              signal={"metric": "metric:error_ratio", "threshold": 0}),
    ])
    assert findings == []


def test_a_threshold_of_zero_counts_as_a_stated_bar():
    """`0` and `false` are meaningful thresholds, not absent ones — the
    acceptance schema says so, and a falsy-check would silently re-report the
    one WMBT in the corpus that actually states a bar."""
    findings = scan_wmbts([
        _wmbt("E004", "likelihood", "maximize",
              signal={"metric": "metric:success_ratio", "threshold": False}),
    ])
    assert findings == []


def test_a_bar_naming_another_metric_is_a_distinct_cause_from_no_bar_at_all():
    """Different findings, different remedies — so they are never one count."""
    findings = {
        f.wmbt_urn: f.cause
        for f in scan_wmbts([
            _wmbt("E005", "likelihood", "minimize"),
            _wmbt("E006", "likelihood", "minimize",
                  signal={"metric": "hardcoded_theme_map_literal_count", "threshold": 0}),
        ])
    }
    assert findings["wmbt:demo:E005"] == CAUSE_NO_BAR
    assert findings["wmbt:demo:E006"] == CAUSE_OFF_MAP


def test_the_scanner_reads_the_mapping_from_the_convention_node():
    """If the scanner keeps its own copy, the node can drift back into claiming
    something nothing checks. The three pairs the issue names must come out of
    the node itself."""
    mapping = dimension_metric_map()

    assert mapping[("likelihood", "minimize")] == "metric:error_ratio"
    assert mapping[("likelihood", "maximize")] == "metric:success_ratio"
    assert mapping[("frequency", "decrease")] == "metric:occurrence_rate"


def test_the_node_dimension_labels_reconcile_with_the_wmbt_schema_enum():
    """The node writes `quantity / amount`; the schema enum says `quantity`.

    Without reconciling them, the 10 real `quantity/maximize` WMBTs the
    convention does map would silently read as unmapped, and the mapping would
    under-claim its own coverage.
    """
    mapping = dimension_metric_map()

    assert mapping[("quantity", "maximize")] == "metric:throughput"
    assert all("/" not in dimension for dimension, _ in mapping)
