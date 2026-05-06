# URN: component:govern-lifecycle:enforcement-substrate:metric_runner:backend:tests
# Runtime: python
# Purpose: Cover the metric runner's discovery, compute/passes, and gate-emission paths against acceptance criteria for issue #412.

"""Unit tests for ``atdd.runners.metric_runner`` (issue #412).

Each test builds an in-memory ``Dict[str, RuleMetadata]`` registry and
writes fixture metric modules under ``tmp_path/.atdd/metrics`` and a
fake toolkit metrics root. The disposition gate is exercised via the
real ``assert_disposition_satisfied`` so the failure-block format stays
in sync with spec §6.

Acceptance criteria (issue #412):

* foo metric returning 5 with threshold 0 produces a Violation.
* Repo-local metric overrides toolkit-shipped metric of the same name.
* Both-mode coexistence: harness + metric runners produce independent
  gate calls (verified by directly invoking the gate twice with the
  same rule_id and inspecting the failure output).
* Custom ``passes(value, threshold) -> value >= threshold`` works for
  minimum-requirement metrics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.coach.validators._violation import Violation
from atdd.runners.metric_runner import (
    VALIDATOR_ID,
    collect_metric_violations,
    discover_metric_module,
    run_metric_runner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta(
    rule_id: str,
    *,
    signal_metric: str | None,
    signal_threshold: object,
    severity: int = 4,
    description: str = "fixture rule",
    fix_hint: str | None = None,
    disposition: str = "strict",
) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        convention_path=Path("/dev/null"),
        severity=severity,
        description=description,
        disposition=disposition,
        fix_hint=fix_hint,
        signal_metric=signal_metric,
        signal_threshold=signal_threshold,
    )


def _write_metric(root: Path, name: str, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return path


# Default metric body: compute returns the bound int, passes is upper-bound.
def _default_metric_body(value: object) -> str:
    return f"""
from pathlib import Path

def compute(repo_root: Path):
    return {value!r}

def passes(value, threshold):
    return value <= threshold
""".lstrip()


# ---------------------------------------------------------------------------
# Acceptance #1 — foo with compute()==5 + threshold=0 produces a Violation
# ---------------------------------------------------------------------------

def test_foo_with_value_5_and_threshold_0_produces_violation(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(5))

    rule_id = "repo.govern-lifecycle.D010-acc-unit-001"
    registry: Dict[str, RuleMetadata] = {
        rule_id: _meta(
            rule_id,
            signal_metric="foo",
            signal_threshold=0,
            description="A single helper replaces every literal",
            fix_hint="No literal appears outside the helper module",
        ),
    }

    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == rule_id
    assert v.severity == 4
    assert v.location == "codebase"
    assert "foo=5" in v.detail
    assert "threshold=0" in v.detail


def test_run_metric_runner_routes_failure_through_gate(tmp_path):
    """End-to-end: run_metric_runner fails pytest with one block per rule."""
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(5))

    rule_id = "repo.govern-lifecycle.D010-acc-unit-001"
    registry = {
        rule_id: _meta(
            rule_id,
            signal_metric="foo",
            signal_threshold=0,
            description="A single helper replaces every literal",
            fix_hint="No literal appears outside the helper module",
        ),
    }

    with pytest.raises(pytest.fail.Exception) as excinfo:
        run_metric_runner(
            registry=registry,
            repo_root=repo_root,
            toolkit_root=toolkit_root,
        )

    msg = str(excinfo.value)
    # Spec §6: failure block carries description: + fix_hint: lines.
    assert f"validator={VALIDATOR_ID}" in msg
    assert f"rule_id={rule_id}" in msg
    assert "description: A single helper replaces every literal" in msg
    assert "fix_hint:    No literal appears outside the helper module" in msg
    assert "foo=5" in msg
    assert "threshold=0" in msg


def test_passing_metric_does_not_emit_violation(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    # compute()==0, threshold=0 → passes (0 <= 0).
    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(0))

    rule_id = "repo.govern-lifecycle.D010-acc-unit-001"
    registry = {rule_id: _meta(rule_id, signal_metric="foo", signal_threshold=0)}

    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


# ---------------------------------------------------------------------------
# Acceptance #2 — Repo-local metric overrides toolkit-shipped metric
# ---------------------------------------------------------------------------

def test_repo_local_metric_overrides_toolkit(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    # Toolkit version says 0 (passes); repo-local says 99 (fails).
    _write_metric(toolkit_root, "shared_metric", _default_metric_body(0))
    _write_metric(repo_root / ".atdd" / "metrics", "shared_metric", _default_metric_body(99))

    lookup = discover_metric_module(
        "shared_metric", repo_root, toolkit_root=toolkit_root,
    )
    assert lookup.source == "repo"
    assert lookup.path is not None
    assert lookup.path.parent == (repo_root / ".atdd" / "metrics").resolve() or \
        lookup.path.parent == repo_root / ".atdd" / "metrics"

    rule_id = "repo.example.override"
    registry = {rule_id: _meta(rule_id, signal_metric="shared_metric", signal_threshold=0)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert len(violations) == 1
    assert "shared_metric=99" in violations[0].detail


def test_toolkit_metric_used_when_no_repo_local(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    _write_metric(toolkit_root, "lines_of_code", _default_metric_body(7))

    lookup = discover_metric_module(
        "lines_of_code", repo_root, toolkit_root=toolkit_root,
    )
    assert lookup.source == "toolkit"

    rule_id = "repo.example.toolkit-only"
    registry = {rule_id: _meta(rule_id, signal_metric="lines_of_code", signal_threshold=10)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []  # 7 <= 10


# ---------------------------------------------------------------------------
# Acceptance #4 — Custom passes for minimum-requirement metrics
# ---------------------------------------------------------------------------

_MINIMUM_REQUIREMENT_BODY = """
from pathlib import Path

def compute(repo_root: Path):
    return 3  # only 3 samples present

def passes(value, threshold):
    return value >= threshold
""".lstrip()


def test_custom_passes_minimum_requirement_fails_when_below_threshold(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    _write_metric(repo_root / ".atdd" / "metrics", "min_samples", _MINIMUM_REQUIREMENT_BODY)

    rule_id = "repo.example.min-samples"
    registry = {
        rule_id: _meta(rule_id, signal_metric="min_samples", signal_threshold=5),
    }
    # 3 < 5 → fails the >= check → violation emitted.
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert len(violations) == 1
    assert "min_samples=3" in violations[0].detail
    assert "threshold=5" in violations[0].detail


def test_custom_passes_minimum_requirement_passes_when_above_threshold(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    _write_metric(repo_root / ".atdd" / "metrics", "min_samples", _MINIMUM_REQUIREMENT_BODY)

    rule_id = "repo.example.min-samples"
    # threshold 2 → 3 >= 2 → passes.
    registry = {rule_id: _meta(rule_id, signal_metric="min_samples", signal_threshold=2)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


# ---------------------------------------------------------------------------
# Acceptance #5 — Both-mode (harness + metric) produces TWO failure blocks
# ---------------------------------------------------------------------------

def test_harness_and_metric_modes_produce_independent_gate_calls(tmp_path):
    """Both runners route through the gate independently per spec §5.3.

    They share the same ``rule_id`` and ``description``/``fix_hint`` (from
    the registry) but distinct ``validator_id`` values. Each call surfaces
    its own failure block.
    """
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()

    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(5))

    rule_id = "repo.govern-lifecycle.D010-acc-unit-001"
    registry = {
        rule_id: _meta(
            rule_id,
            signal_metric="foo",
            signal_threshold=0,
            description="single helper replaces every literal",
            fix_hint="No literal outside helper module",
        ),
    }

    # Metric mode call.
    metric_violations = collect_metric_violations(
        registry, repo_root, toolkit_root=toolkit_root,
    )
    assert len(metric_violations) == 1

    with pytest.raises(pytest.fail.Exception) as metric_exc:
        assert_disposition_satisfied(
            validator_id=VALIDATOR_ID,
            violations=metric_violations,
            registry=registry,
            repo_root=repo_root,
        )
    metric_msg = str(metric_exc.value)
    assert f"validator={VALIDATOR_ID}" in metric_msg
    assert f"rule_id={rule_id}" in metric_msg
    assert "description: single helper replaces every literal" in metric_msg
    assert "fix_hint:    No literal outside helper module" in metric_msg

    # Harness mode call: same rule_id, different validator_id, distinct location.
    harness_validator = "test_theme_map::test_no_hardcoded_literals"
    harness_violation = Violation(
        rule_id=rule_id,
        severity=4,
        location="src/foo.py:42",
        detail="hardcoded literal found",
    )
    with pytest.raises(pytest.fail.Exception) as harness_exc:
        assert_disposition_satisfied(
            validator_id=harness_validator,
            violations=[harness_violation],
            registry=registry,
            repo_root=repo_root,
        )
    harness_msg = str(harness_exc.value)
    assert f"validator={harness_validator}" in harness_msg
    assert f"rule_id={rule_id}" in harness_msg
    # Same enrichment fields on both blocks.
    assert "description: single helper replaces every literal" in harness_msg
    assert "fix_hint:    No literal outside helper module" in harness_msg

    # The two failure blocks are independent: distinct validator_ids.
    assert VALIDATOR_ID in metric_msg
    assert VALIDATOR_ID not in harness_msg
    assert harness_validator in harness_msg
    assert harness_validator not in metric_msg


# ---------------------------------------------------------------------------
# Skip semantics — missing impl, missing threshold, missing metric
# ---------------------------------------------------------------------------

def test_missing_metric_implementation_silently_skipped(tmp_path):
    """Per #410 conformance rule, runtime does NOT double-emit on missing impl."""
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    # No metric file written under either root.

    rule_id = "repo.example.missing-impl"
    registry = {rule_id: _meta(rule_id, signal_metric="ghost", signal_threshold=0)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


def test_metric_without_threshold_silently_skipped(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(5))

    rule_id = "repo.example.no-threshold"
    registry = {rule_id: _meta(rule_id, signal_metric="foo", signal_threshold=None)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


def test_threshold_without_metric_silently_skipped(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(5))

    rule_id = "repo.example.no-metric"
    registry = {rule_id: _meta(rule_id, signal_metric=None, signal_threshold=0)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


def test_module_missing_compute_silently_skipped(tmp_path):
    """Module without compute() is treated as absent (no double-emit)."""
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    body = """
def passes(value, threshold):
    return value <= threshold
""".lstrip()
    _write_metric(repo_root / ".atdd" / "metrics", "no_compute", body)

    rule_id = "repo.example.no-compute"
    registry = {rule_id: _meta(rule_id, signal_metric="no_compute", signal_threshold=0)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


def test_module_missing_passes_silently_skipped(tmp_path):
    """Module without passes() is treated as absent (no double-emit)."""
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    body = """
from pathlib import Path

def compute(repo_root: Path):
    return 5
""".lstrip()
    _write_metric(repo_root / ".atdd" / "metrics", "no_passes", body)

    rule_id = "repo.example.no-passes"
    registry = {rule_id: _meta(rule_id, signal_metric="no_passes", signal_threshold=0)}
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert violations == []


# ---------------------------------------------------------------------------
# Bool-metric conventional encoding (spec §4.5)
# ---------------------------------------------------------------------------

_BOOL_METRIC_BODY = """
from pathlib import Path

def compute(repo_root: Path):
    return True  # violation present

def passes(value, threshold):
    return value <= threshold
""".lstrip()


def test_bool_metric_true_with_threshold_false_fails(tmp_path):
    """Spec §4.5: bool metric encoding True=='violation', threshold False, default passes."""
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    _write_metric(repo_root / ".atdd" / "metrics", "duplicate_side_effects", _BOOL_METRIC_BODY)

    rule_id = "repo.example.bool-metric"
    registry = {
        rule_id: _meta(
            rule_id,
            signal_metric="duplicate_side_effects",
            signal_threshold=False,
        ),
    }
    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    # passes(True, False): True <= False → False → fails.
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Single gate call groups multiple failures by rule_id
# ---------------------------------------------------------------------------

def test_multiple_failing_rules_emit_one_block_each(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    _write_metric(repo_root / ".atdd" / "metrics", "alpha", _default_metric_body(5))
    _write_metric(repo_root / ".atdd" / "metrics", "beta", _default_metric_body(7))

    registry = {
        "repo.example.alpha": _meta(
            "repo.example.alpha", signal_metric="alpha", signal_threshold=0,
        ),
        "repo.example.beta": _meta(
            "repo.example.beta", signal_metric="beta", signal_threshold=0,
        ),
    }
    with pytest.raises(pytest.fail.Exception) as excinfo:
        run_metric_runner(
            registry=registry, repo_root=repo_root, toolkit_root=toolkit_root,
        )
    msg = str(excinfo.value)
    assert "rule_id=repo.example.alpha" in msg
    assert "rule_id=repo.example.beta" in msg
    # Both blocks share the same validator_id (one runner, multiple rules).
    assert msg.count(f"validator={VALIDATOR_ID}") == 2


# ---------------------------------------------------------------------------
# Aliased rule registered twice in the registry should not double-emit
# ---------------------------------------------------------------------------

def test_aliased_rule_emits_one_violation(tmp_path):
    repo_root = tmp_path
    toolkit_root = tmp_path / "_toolkit_metrics"
    toolkit_root.mkdir()
    _write_metric(repo_root / ".atdd" / "metrics", "foo", _default_metric_body(5))

    rule_id = "repo.example.canonical"
    meta = _meta(rule_id, signal_metric="foo", signal_threshold=0)
    # The registry indexes both the canonical id and aliases at the same
    # RuleMetadata; the runner must dedupe.
    registry = {rule_id: meta, "LEGACY-FOO-001": meta}

    violations = collect_metric_violations(registry, repo_root, toolkit_root=toolkit_root)
    assert len(violations) == 1
    assert violations[0].rule_id == rule_id
