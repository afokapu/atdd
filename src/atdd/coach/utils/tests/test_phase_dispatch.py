# URN: urn:atdd:test:coach:utils:phase_dispatch
# Issue: #416

"""Tests for the coach phase-driven dispatcher (substrate spec v12 §8.1).

Covers:

* Pure-function selector against in-memory ``RuleMetadata`` lists:
  - ``phase=X`` rules selected at coach phase X.
  - ``phase=GREEN`` rules selected at RED ("RED expects red", §8.1 ¶5).
  - REFACTOR sweeps every strict-disposition rule (toolkit + repo).
  - Toolkit rules excluded outside REFACTOR.
  - Security-rule branch: ``bound_acceptance_urn`` resolution governs
    dispatch phase (§8.1 line 584).
  - Determinism: result ordered by ``rule_id``.
  - Phase normalization (case-insensitive) and unknown-phase rejection.
* Integration test against the fixture WMBT
  ``src/atdd/tester/validators/fixtures/phase_dispatch/mixed_phases.yaml``
  driven through the live walker → registry path.
* ``classify_violation`` honors §4.1 expected-vs-regression at RED.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

import pytest

from atdd.coach.utils.phase_dispatch import (
    PhaseDispatchError,
    classify_violation,
    select_validator_set,
)
from atdd.coach.utils.rule_binding import RuleMetadata


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# In-memory fixture builders
# ---------------------------------------------------------------------------
def _make_rule(
    rule_id: str,
    *,
    phase: str = None,
    disposition: str = "strict",
    bound_acceptance_urn: str = None,
) -> RuleMetadata:
    """Construct a minimal ``RuleMetadata`` for selector unit tests."""
    return RuleMetadata(
        rule_id=rule_id,
        severity=4,
        description=f"fixture rule {rule_id}",
        recipe=None,
        introduced_in=None,
        source_path=Path("/tmp/fake.yaml"),
        disposition=disposition,
        validator=None,
        fix_hint=None,
        aliases=(),
        phase=phase,
        bound_acceptance_urn=bound_acceptance_urn,
    )


def _ids(rules: List[RuleMetadata]) -> List[str]:
    return [r.rule_id for r in rules]


# ---------------------------------------------------------------------------
# Pure-function selector behavior
# ---------------------------------------------------------------------------
def test_green_phase_selects_only_green_repo_rules():
    """A coach session at GREEN selects only repo rules with ``phase: GREEN``."""
    registry = [
        _make_rule("repo.fixture.D001-acc-unit-001", phase="RED"),
        _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN"),
        _make_rule("repo.fixture.D001-acc-unit-003", phase="REFACTOR"),
    ]
    selected = select_validator_set("GREEN", registry=registry)
    assert _ids(selected) == ["repo.fixture.D001-acc-unit-002"]


def test_red_phase_selects_red_and_green_rules_per_red_expects_red():
    """At RED, both phase=RED and phase=GREEN repo rules are selected (§8.1 ¶5).

    The phase=GREEN rules represent the "RED expects red" override:
    coach exercises the GREEN contract at RED so violations confirm the
    contract currently fails (expected at RED, not at GREEN).
    """
    registry = [
        _make_rule("repo.fixture.D001-acc-unit-001", phase="RED"),
        _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN"),
        _make_rule("repo.fixture.D001-acc-unit-003", phase="REFACTOR"),
    ]
    selected = select_validator_set("RED", registry=registry)
    assert _ids(selected) == [
        "repo.fixture.D001-acc-unit-001",
        "repo.fixture.D001-acc-unit-002",
    ]


def test_refactor_sweeps_every_strict_rule_regardless_of_phase():
    """REFACTOR sweeps every strict-disposition rule (toolkit + repo) per §8.1 ¶4."""
    registry = [
        _make_rule("repo.fixture.D001-acc-unit-001", phase="RED"),
        _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN"),
        _make_rule("repo.fixture.D001-acc-unit-003", phase="REFACTOR"),
        _make_rule("coder.fixture.toolkit-strict", phase=None),
        _make_rule(
            "coder.fixture.toolkit-advisory", phase=None, disposition="advisory"
        ),
    ]
    selected = select_validator_set("REFACTOR", registry=registry)
    # Every strict rule appears (toolkit AND repo); the advisory one
    # does not.
    assert _ids(selected) == [
        "coder.fixture.toolkit-strict",
        "repo.fixture.D001-acc-unit-001",
        "repo.fixture.D001-acc-unit-002",
        "repo.fixture.D001-acc-unit-003",
    ]


def test_smoke_phase_selects_only_smoke_repo_rules():
    """SMOKE selects rules whose ``phase: SMOKE``, no fallback."""
    registry = [
        _make_rule("repo.fixture.D001-acc-unit-001", phase="RED"),
        _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN"),
        _make_rule("repo.fixture.D001-acc-unit-003", phase="REFACTOR"),
        _make_rule("repo.fixture.D001-acc-unit-004", phase="SMOKE"),
    ]
    selected = select_validator_set("SMOKE", registry=registry)
    assert _ids(selected) == ["repo.fixture.D001-acc-unit-004"]


def test_toolkit_rules_excluded_outside_refactor():
    """Toolkit-archetype rules are not selected at RED/GREEN/SMOKE.

    Phase-driven dispatch surfaces *repo* rules per §8.1; toolkit rules
    continue to be selected by archetype (handled separately by
    ``atdd validate``). REFACTOR is the only phase that pulls toolkit
    rules through the selector — and only when their disposition is
    ``strict`` (sweep semantics).
    """
    registry = [
        _make_rule("coder.fixture.toolkit-strict-rule", phase=None),
        _make_rule("repo.fixture.D001-acc-unit-001", phase="GREEN"),
    ]
    for phase in ("RED", "GREEN", "SMOKE"):
        selected = select_validator_set(phase, registry=registry)
        assert all(r.rule_id.startswith("repo.") for r in selected), (
            f"toolkit rule leaked into selection at {phase}"
        )


def test_unknown_phase_raises():
    with pytest.raises(PhaseDispatchError):
        select_validator_set("PLANNED", registry=[])
    with pytest.raises(PhaseDispatchError):
        select_validator_set("", registry=[])


def test_phase_is_case_insensitive():
    """The selector normalizes phase to upper-case internally."""
    registry = [_make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN")]
    assert _ids(select_validator_set("green", registry=registry)) == [
        "repo.fixture.D001-acc-unit-002"
    ]
    assert _ids(select_validator_set("Green", registry=registry)) == [
        "repo.fixture.D001-acc-unit-002"
    ]


def test_selection_is_deterministic_and_dedup():
    """Selected rules sort by ``rule_id`` and are deduped at REFACTOR.

    A repo rule with phase=REFACTOR and disposition=strict matches both
    set 1 (phase match) and set 3 (REFACTOR sweep). The selector emits
    it once.
    """
    registry = [
        _make_rule("repo.fixture.D001-acc-unit-002", phase="REFACTOR"),
        _make_rule("repo.fixture.D001-acc-unit-001", phase="REFACTOR"),
    ]
    ids = _ids(select_validator_set("REFACTOR", registry=registry))
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))  # no duplicates


# ---------------------------------------------------------------------------
# Security-rule branch (§8.1 line 584)
# ---------------------------------------------------------------------------
def _security_registry():
    """Registry mixing a bound acceptance with a security rule pointing at it."""
    return [
        _make_rule("repo.feature-x.D005-acc-http-001", phase="GREEN"),
        # Security rule's own phase is intentionally *wrong* — dispatch
        # must read the bound rule's phase, not this one.
        _make_rule(
            "repo.feature-x.security-rule-001",
            phase="REFACTOR",
            bound_acceptance_urn="repo.feature-x.D005-acc-http-001",
        ),
    ]


def test_security_rule_dispatches_on_bound_acceptance_phase():
    """A security rule's bound-acceptance phase governs dispatch (§8.1 line 584).

    The bound acceptance is at GREEN, so the security rule activates at
    GREEN even though the security rule's *own* ``phase`` claims REFACTOR.
    """
    from atdd.coach.utils import rule_binding as rb

    rb.clear_cache()
    registry = _security_registry()
    # Seed the registry cache directly so bind_rule(bound_urn) resolves
    # in the selector's ``_phase_for_dispatch`` helper.
    rb._REGISTRY_CACHE = {meta.rule_id: [meta] for meta in registry}
    try:
        selected_green = _ids(select_validator_set("GREEN", registry=registry))
        # Both rules activate at GREEN: the bound acceptance directly,
        # the security rule via bound_acceptance_urn → GREEN.
        assert "repo.feature-x.security-rule-001" in selected_green
        assert "repo.feature-x.D005-acc-http-001" in selected_green
        # At REFACTOR the strict-sweep also pulls the security rule in
        # (it's strict-disposition); we just assert presence.
        selected_refactor = _ids(
            select_validator_set("REFACTOR", registry=registry)
        )
        assert "repo.feature-x.security-rule-001" in selected_refactor
    finally:
        rb.clear_cache()


def test_security_rule_with_unresolved_binding_is_skipped():
    """An unresolvable ``bound_acceptance_urn`` causes the rule to be skipped.

    Per spec §7.3, the substrate enforcement rule
    ``security-rule-must-have-acceptance-ref-resolved`` surfaces this at
    PLANNED phase. The dispatch selector silently skips so a stale
    binding does not poison runtime selection.
    """
    from atdd.coach.utils import rule_binding as rb

    rb.clear_cache()
    registry = [
        _make_rule(
            "repo.feature-x.security-rule-001",
            phase="GREEN",
            bound_acceptance_urn="repo.does-not-exist.acc-missing",
        ),
    ]
    rb._REGISTRY_CACHE = {meta.rule_id: [meta] for meta in registry}
    try:
        selected = select_validator_set("GREEN", registry=registry)
        assert _ids(selected) == []
    finally:
        rb.clear_cache()


# ---------------------------------------------------------------------------
# Integration test against the fixture (acceptance criterion)
# ---------------------------------------------------------------------------
@pytest.fixture
def fixture_repo_with_mixed_phases(tmp_path: Path) -> Path:
    """Stand up a stand-in repo seeded with the mixed_phases.yaml fixture.

    The walker discovers WMBT YAML at ``plan/<wagon>/[DLPCEMYRK]NNN.yaml``;
    the fixture file lives elsewhere (under ``tester/validators/fixtures/``)
    so we copy it into the conventional layout.
    """
    fixture_src = (
        Path(__file__).resolve().parents[3]
        / "tester"
        / "validators"
        / "fixtures"
        / "phase_dispatch"
        / "mixed_phases.yaml"
    )
    assert fixture_src.is_file(), (
        f"fixture missing at {fixture_src}; expected copy under "
        f"src/atdd/tester/validators/fixtures/phase_dispatch/"
    )
    plan_dir = tmp_path / "plan" / "phase-dispatch"
    plan_dir.mkdir(parents=True)
    shutil.copy(fixture_src, plan_dir / "D001.yaml")
    return tmp_path


def test_select_validator_set_against_mixed_phases_fixture(
    fixture_repo_with_mixed_phases: Path,
):
    """Issue #416 acceptance criterion — integration against the fixture.

    A coach session at:
      - RED      selects { unit-001, unit-002 } (RED expects red)
      - GREEN    selects { unit-002 }
      - SMOKE    selects { } (no fixture rule pinned to SMOKE)
      - REFACTOR sweeps { unit-001, unit-002, unit-003 } (all strict)
    """
    from atdd.coach.utils import rule_binding as rb

    rb.clear_cache(override_repo_root=fixture_repo_with_mixed_phases)
    try:
        red = _ids(select_validator_set("RED"))
        assert red == [
            "repo.phase-dispatch.D001-acc-unit-001",
            "repo.phase-dispatch.D001-acc-unit-002",
        ]

        green = _ids(select_validator_set("GREEN"))
        assert green == ["repo.phase-dispatch.D001-acc-unit-002"]

        smoke = _ids(select_validator_set("SMOKE"))
        assert smoke == []

        refactor = _ids(select_validator_set("REFACTOR"))
        # Every strict-disposition repo rule from the fixture appears.
        # Toolkit-strict rules also appear (they are swept in REFACTOR);
        # filter the assertion to repo-rules so the test stays hermetic
        # against unrelated toolkit churn.
        repo_subset = [r for r in refactor if r.startswith("repo.phase-dispatch.")]
        assert repo_subset == [
            "repo.phase-dispatch.D001-acc-unit-001",
            "repo.phase-dispatch.D001-acc-unit-002",
            "repo.phase-dispatch.D001-acc-unit-003",
        ]
    finally:
        rb.clear_cache()


# ---------------------------------------------------------------------------
# classify_violation — coach v6 §4.1 expected-vs-regression
# ---------------------------------------------------------------------------
def test_classify_violation_red_expects_red_for_green_rule():
    """At RED, a phase=GREEN rule's violation classifies as ``expected``."""
    rule = _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN")
    assert classify_violation("RED", rule, violation_emitted=True) == "expected"


def test_classify_violation_red_expects_red_no_violation_is_regression():
    """At RED, a phase=GREEN rule passing classifies as ``regression``.

    The GREEN contract is already passing at RED — coach surfaces this
    so the agent doesn't silently skip the GREEN write.
    """
    rule = _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN")
    assert classify_violation("RED", rule, violation_emitted=False) == "regression"


def test_classify_violation_green_phase_violation_is_failure():
    """At GREEN, a phase=GREEN rule's violation classifies as ``failure``."""
    rule = _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN")
    assert classify_violation("GREEN", rule, violation_emitted=True) == "failure"


def test_classify_violation_green_phase_no_violation_is_pass():
    rule = _make_rule("repo.fixture.D001-acc-unit-002", phase="GREEN")
    assert classify_violation("GREEN", rule, violation_emitted=False) == "pass"
