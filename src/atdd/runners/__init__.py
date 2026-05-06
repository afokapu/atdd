# URN: component:govern-lifecycle:enforcement-substrate:runners:backend:domain
# Runtime: python
# Purpose: Toolkit-shipped runners that read RuleMetadata, dispatch enforcement, and route Violations through the disposition gate.

"""Substrate runners (spec v12 §4.5).

Each runner consumes the rule registry built by
``atdd.coach.utils.rule_id_registry.build_registry`` and emits violations
through ``atdd.coach.utils.disposition_gate.assert_disposition_satisfied``.

Three runners are defined by the substrate:

* harness-mode  — pytest plugin (per-test rule binding); see substrate spec.
* metric-mode   — single computation per rule (this package, ``metric_runner``).
* security-mode — single resolution per rule (separate runner, not in this issue).
"""
