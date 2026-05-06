# URN: component:govern-lifecycle:enforcement-substrate:test_acceptance_violation_fixtures:backend:tests
# Runtime: python
# Purpose: Fixture-based RED tests proving the five substrate enforcement validators (#410) emit Violations with verbatim rule-IDs from spec §7.3.

"""Tests for the substrate Class 1 enforcement validators (issue #410).

Each test writes an intentionally broken plan/ tree under ``tmp_path``,
calls the validator's ``collect_violations(repo_root)`` directly, and
asserts the returned ``Violation.rule_id`` matches the verbatim id from
``acceptance-violation.convention.yaml``.

The five rules under test:
  - tester.acceptance-violation.acceptance-must-be-measurable
  - tester.acceptance-violation.acceptance-must-declare-phase
  - tester.acceptance-violation.disposition-must-not-be-declared
  - tester.acceptance-violation.validator-binding-must-be-bidirectional
  - tester.acceptance-violation.metric-implementation-must-exist

Each test uses fresh ``clear_cache`` so the registry walker re-reads the
fixture's plan/ on every invocation.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from atdd.coach.utils.rule_binding import clear_cache


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


_WMBT_HEADER = """
    urn: "wmbt:foo-wagon:D001"
    step: "define"
    direction: "minimize"
    dimension: "quantity"
    object_of_control: "thing"
    context_clarifier: "fixture"
    lens: "functional.sustainability"
    statement: "minimize thing"
    acceptances:
"""


# ---------------------------------------------------------------------------
# acceptance-must-be-measurable
# ---------------------------------------------------------------------------
def test_measurability_fires_when_no_harness_and_no_signal(tmp_path: Path):
    """Acceptance with neither harness nor signal fires the rule."""
    from atdd.tester.validators.test_acceptance_measurable import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D001.yaml",
        _WMBT_HEADER + """
          - identity:
              urn: "acc:foo-wagon:D001-UNIT-001"
              phase: GREEN
              purpose: "no harness, no signal — unenforceable"
            given: { abstract: ["..."] }
            when:  { abstract: "..." }
            then:  { abstract: ["..."] }
    """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.acceptance-must-be-measurable"
    )
    assert "acc:foo-wagon:D001-UNIT-001" in violations[0].detail


def test_measurability_fires_when_signal_metric_without_threshold(tmp_path: Path):
    """signal.metric without signal.threshold is half-declared and fails."""
    from atdd.tester.validators.test_acceptance_measurable import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D001.yaml",
        _WMBT_HEADER + """
          - identity:
              urn: "acc:foo-wagon:D001-METRIC-001"
              phase: GREEN
              purpose: "metric set, threshold missing"
            signal:
              metric: "some_count"
            given: { abstract: ["x"] }
            when:  { abstract: "y" }
            then:  { abstract: ["z"] }
    """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.acceptance-must-be-measurable"
    )


def test_measurability_passes_when_harness_set(tmp_path: Path):
    from atdd.tester.validators.test_acceptance_measurable import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D001.yaml",
        _WMBT_HEADER + """
          - identity:
              urn: "acc:foo-wagon:D001-UNIT-001"
              phase: GREEN
              purpose: "harness set"
            harness:
              type: unit
              category: backend
            given: { abstract: ["x"] }
            when:  { abstract: "y" }
            then:  { abstract: ["z"] }
    """,
    )

    assert collect_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# acceptance-must-declare-phase
# ---------------------------------------------------------------------------
def test_phase_fires_when_phase_missing(tmp_path: Path):
    from atdd.tester.validators.test_acceptance_phase import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D002.yaml",
        _WMBT_HEADER.replace("D001", "D002") + """
          - identity:
              urn: "acc:foo-wagon:D002-UNIT-001"
              purpose: "no phase declared"
            harness: { type: unit }
    """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.acceptance-must-declare-phase"
    )


def test_phase_fires_when_phase_invalid(tmp_path: Path):
    from atdd.tester.validators.test_acceptance_phase import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D003.yaml",
        _WMBT_HEADER.replace("D001", "D003") + """
          - identity:
              urn: "acc:foo-wagon:D003-UNIT-001"
              phase: SHIPPED
              purpose: "non-canonical phase value"
            harness: { type: unit }
    """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.acceptance-must-declare-phase"
    )
    assert "SHIPPED" in violations[0].detail


def test_phase_passes_for_canonical_phases(tmp_path: Path):
    from atdd.tester.validators.test_acceptance_phase import collect_violations

    body_template = _WMBT_HEADER + """
          - identity:
              urn: "acc:foo-wagon:D001-UNIT-001"
              phase: {phase}
              purpose: "canonical phase"
            harness: { type: unit }
    """
    for phase in ("RED", "GREEN", "SMOKE", "REFACTOR"):
        target = tmp_path / "plan" / "foo-wagon" / "D001.yaml"
        _write(target, body_template.replace("{phase}", phase))
        assert collect_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# disposition-must-not-be-declared
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("disposition_value", ["strict", "advisory", "suppress-and-clean"])
def test_disposition_fires_for_any_value_in_wmbt(tmp_path: Path, disposition_value: str):
    """The validator rejects ANY disposition value — strict included."""
    from atdd.tester.validators.test_acceptance_disposition import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D004.yaml",
        _WMBT_HEADER.replace("D001", "D004") + f"""
          - identity:
              urn: "acc:foo-wagon:D004-UNIT-001"
              phase: GREEN
              purpose: "carries forbidden disposition"
            harness: {{ type: unit }}
            disposition: {disposition_value}
    """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.disposition-must-not-be-declared"
    )
    assert "disposition" in violations[0].detail


def test_disposition_fires_in_train_yaml(tmp_path: Path):
    from atdd.tester.validators.test_acceptance_disposition import collect_violations

    (tmp_path / "plan" / "_trains").mkdir(parents=True)
    _write(
        tmp_path / "plan" / "_trains" / "0001-x.yaml",
        """
        train_id: "0001-x"
        title: "x"
        description: "x"
        themes: ["t"]
        participants: ["wagon:foo-wagon"]
        sequence: []
        acceptances:
          - identity:
              urn: "acc:0001-x:idempotent"
              phase: GREEN
              purpose: "p"
            harness: { type: e2e }
            disposition: strict
        """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.disposition-must-not-be-declared"
    )


def test_disposition_in_feature_yaml_under_security_abuse_cases(tmp_path: Path):
    """Spec §7.3: feature.yaml::security.abuse_cases[] is in scope."""
    from atdd.tester.validators.test_acceptance_disposition import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "feature.yaml",
        """
        urn: "feature:foo-wagon:bar"
        # disposition outside security is ignored — only abuse_cases is scoped.
        security:
          abuse_cases:
            - id: "001"
              threat: "xss"
              acceptance_ref: "acc:foo-wagon:D001-UNIT-001"
              disposition: advisory
        """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.disposition-must-not-be-declared"
    )


def test_disposition_passes_when_repo_yaml_is_clean(tmp_path: Path):
    from atdd.tester.validators.test_acceptance_disposition import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D005.yaml",
        _WMBT_HEADER.replace("D001", "D005") + """
          - identity:
              urn: "acc:foo-wagon:D005-UNIT-001"
              phase: GREEN
              purpose: "clean — no disposition"
            harness: { type: unit }
    """,
    )

    assert collect_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# validator-binding-must-be-bidirectional
# ---------------------------------------------------------------------------
def test_repo_binding_fires_when_acceptance_has_no_anchored_test(tmp_path: Path):
    from atdd.tester.validators.test_repo_validator_binding import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D006.yaml",
        _WMBT_HEADER.replace("D001", "D006") + """
          - identity:
              urn: "acc:foo-wagon:D006-UNIT-001"
              phase: GREEN
              purpose: "harness declared but no test anchored"
            harness: { type: unit }
    """,
    )

    violations = collect_violations(tmp_path)
    assert any(
        v.rule_id == "tester.acceptance-violation.validator-binding-must-be-bidirectional"
        for v in violations
    )
    detail = next(v.detail for v in violations)
    assert "acc:foo-wagon:D006-UNIT-001" in detail


def test_repo_binding_fires_when_test_anchors_to_unknown_acceptance(tmp_path: Path):
    """Reverse pass: a test header naming an acc URN that doesn't exist fires."""
    from atdd.tester.validators.test_repo_validator_binding import collect_violations

    # No plan/ at all — fresh repo.
    (tmp_path / "plan").mkdir()
    test_dir = tmp_path / "python" / "foo_wagon" / "tests"
    _write(
        test_dir / "test_orphan.py",
        """
        # URN: test:foo-wagon:orphan
        # Acceptance: acc:foo-wagon:D999-UNIT-001
        # WMBT: wmbt:foo-wagon:D999
        # Phase: GREEN
        # Layer: domain

        def test_orphan():
            pass
        """,
    )

    violations = collect_violations(tmp_path)
    assert any(
        v.rule_id == "tester.acceptance-violation.validator-binding-must-be-bidirectional"
        and "acc:foo-wagon:D999-UNIT-001" in v.detail
        for v in violations
    )


def test_repo_binding_passes_when_pair_is_bidirectional(tmp_path: Path):
    from atdd.tester.validators.test_repo_validator_binding import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D007.yaml",
        _WMBT_HEADER.replace("D001", "D007") + """
          - identity:
              urn: "acc:foo-wagon:D007-UNIT-001"
              phase: GREEN
              purpose: "binding ok"
            harness: { type: unit }
    """,
    )
    _write(
        tmp_path / "python" / "foo_wagon" / "tests" / "test_d007.py",
        """
        # URN: test:foo-wagon:d007
        # Acceptance: acc:foo-wagon:D007-UNIT-001
        # WMBT: wmbt:foo-wagon:D007
        # Phase: GREEN
        # Layer: domain

        def test_d007():
            pass
        """,
    )

    assert collect_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# metric-implementation-must-exist
# ---------------------------------------------------------------------------
def test_metric_implementation_fires_when_metric_module_missing(tmp_path: Path):
    """signal.metric=foo, no foo.py in either lookup root → rule fires."""
    from atdd.tester.validators.test_metric_implementation import collect_violations

    _write(
        tmp_path / "plan" / "foo-wagon" / "D008.yaml",
        _WMBT_HEADER.replace("D001", "D008") + """
          - identity:
              urn: "acc:foo-wagon:D008-METRIC-001"
              phase: GREEN
              purpose: "metric with no impl"
            signal:
              metric: "definitely_not_a_real_metric_name_xyz"
              threshold: 0
    """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.metric-implementation-must-exist"
    )
    assert "definitely_not_a_real_metric_name_xyz" in violations[0].detail


def test_metric_implementation_fires_when_module_lacks_compute(tmp_path: Path):
    """File exists but exports no compute() callable → rule fires."""
    from atdd.tester.validators.test_metric_implementation import collect_violations

    metric_name = "fixture_metric_no_compute"
    _write(
        tmp_path / "plan" / "foo-wagon" / "D009.yaml",
        _WMBT_HEADER.replace("D001", "D009") + f"""
          - identity:
              urn: "acc:foo-wagon:D009-METRIC-001"
              phase: GREEN
              purpose: "metric file exists but no compute()"
            signal:
              metric: "{metric_name}"
              threshold: 0
    """,
    )
    _write(
        tmp_path / ".atdd" / "metrics" / f"{metric_name}.py",
        """
        # No compute function defined here.
        def something_else():
            return 0
        """,
    )

    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    assert (
        violations[0].rule_id
        == "tester.acceptance-violation.metric-implementation-must-exist"
    )


def test_metric_implementation_passes_when_repo_local_module_provides_compute(
    tmp_path: Path,
):
    """Repo-local <repo>/.atdd/metrics/foo.py with compute() satisfies the rule."""
    from atdd.tester.validators.test_metric_implementation import collect_violations

    metric_name = "fixture_metric_ok"
    _write(
        tmp_path / "plan" / "foo-wagon" / "D010.yaml",
        _WMBT_HEADER.replace("D001", "D010") + f"""
          - identity:
              urn: "acc:foo-wagon:D010-METRIC-001"
              phase: GREEN
              purpose: "happy path"
            signal:
              metric: "{metric_name}"
              threshold: 0
    """,
    )
    _write(
        tmp_path / ".atdd" / "metrics" / f"{metric_name}.py",
        """
        def compute(repo_root):
            return 0

        def passes(value, threshold):
            return value <= threshold
        """,
    )

    assert collect_violations(tmp_path) == []
