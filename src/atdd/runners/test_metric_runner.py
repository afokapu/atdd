# URN: component:govern-lifecycle:enforcement-substrate:test_metric_runner:backend:tests
# Runtime: python
# Purpose: Single pytest entry point for the metric-mode runner (spec v12 §4.5).

"""Pytest anchor for the metric-mode runner (issue #412).

Substrate spec v12 §4.5 anchors the metric runner at
``test_metric_runner::test_metric_threshold_satisfied``. Every rule whose
``signal.metric`` fails its ``passes(value, threshold)`` check surfaces as
a failure block in this single pytest item, grouped by ``rule_id`` by the
disposition gate.

The implementation lives in ``atdd.runners.metric_runner.run_metric_runner``;
this module exists so that the validator_id matches the spec literally.
"""

from __future__ import annotations

from atdd.runners.metric_runner import run_metric_runner


def test_metric_threshold_satisfied() -> None:
    """Run every metric-mode rule and route failures through the gate."""
    run_metric_runner()
