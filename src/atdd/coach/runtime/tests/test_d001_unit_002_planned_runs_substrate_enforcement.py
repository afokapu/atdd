# URN: test:dispatch-validators:planned-runs-substrate-enforcement
# Acceptance: acc:dispatch-validators:D001-UNIT-002-planned-runs-substrate-enforcement
# WMBT: wmbt:dispatch-validators:D001
# Phase: GREEN
# Layer: domain

"""AC-UNIT-002: PLANNED phase runs substrate enforcement validators.

Per spec §6.5 PLANNED row:
  - Toolkit slice: atdd.planner.validators.* + atdd.tester.validators.acceptance-violation.*
  - Substrate enforcement includes all five rules from
    acceptance-violation.convention.yaml:
      1. acceptance-must-be-measurable
      2. acceptance-must-declare-phase
      3. disposition-must-not-be-declared
      4. validator-binding-must-be-bidirectional
      5. metric-implementation-must-exist
"""

from pathlib import Path

import pytest

from atdd.coach.runtime.validator_selection import ValidatorSet, build_validator_set
from atdd.coach.utils.coach_config import CoachConfig, ValidatorsConfig
from atdd.coach.utils.rule_binding import RuleMetadata


_DUMMY_PATH = Path("/dev/null")

# The five substrate enforcement rule IDs from acceptance-violation.convention.yaml
SUBSTRATE_ENFORCEMENT_IDS = [
    "tester.acceptance-violation.acceptance-must-be-measurable",
    "tester.acceptance-violation.acceptance-must-declare-phase",
    "tester.acceptance-violation.disposition-must-not-be-declared",
    "tester.acceptance-violation.validator-binding-must-be-bidirectional",
    "tester.acceptance-violation.metric-implementation-must-exist",
]


def _make_toolkit_rule(rule_id: str) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=3,
        description=f"test {rule_id}",
        recipe=None,
        introduced_in=None,
        source_path=_DUMMY_PATH,
        disposition="strict",
    )


class TestPlannedSubstrateEnforcement:
    """AC-UNIT-002: PLANNED includes all five substrate enforcement rules."""

    def test_all_five_substrate_enforcement_rules_present(self):
        """All five acceptance-violation.* rules are in PLANNED toolkit slice."""
        registry = [_make_toolkit_rule(rid) for rid in SUBSTRATE_ENFORCEMENT_IDS]
        # Add some non-matching rules
        registry.extend([
            _make_toolkit_rule("tester.red.convention"),
            _make_toolkit_rule("coder.dead-code.reachability"),
        ])

        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        for expected_id in SUBSTRATE_ENFORCEMENT_IDS:
            assert expected_id in toolkit_ids, (
                f"Substrate enforcement rule {expected_id!r} missing from PLANNED toolkit slice"
            )

    def test_acceptance_must_be_measurable(self):
        """acceptance-must-be-measurable is present."""
        registry = [_make_toolkit_rule("tester.acceptance-violation.acceptance-must-be-measurable")]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "tester.acceptance-violation.acceptance-must-be-measurable" in toolkit_ids

    def test_acceptance_must_declare_phase(self):
        """acceptance-must-declare-phase is present."""
        registry = [_make_toolkit_rule("tester.acceptance-violation.acceptance-must-declare-phase")]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "tester.acceptance-violation.acceptance-must-declare-phase" in toolkit_ids

    def test_disposition_must_not_be_declared(self):
        """disposition-must-not-be-declared is present."""
        registry = [_make_toolkit_rule("tester.acceptance-violation.disposition-must-not-be-declared")]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "tester.acceptance-violation.disposition-must-not-be-declared" in toolkit_ids

    def test_validator_binding_must_be_bidirectional(self):
        """validator-binding-must-be-bidirectional is present."""
        registry = [_make_toolkit_rule("tester.acceptance-violation.validator-binding-must-be-bidirectional")]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "tester.acceptance-violation.validator-binding-must-be-bidirectional" in toolkit_ids

    def test_metric_implementation_must_exist(self):
        """metric-implementation-must-exist is present."""
        registry = [_make_toolkit_rule("tester.acceptance-violation.metric-implementation-must-exist")]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "tester.acceptance-violation.metric-implementation-must-exist" in toolkit_ids


class TestPlannedPlannerValidators:
    """AC-UNIT-002: PLANNED includes atdd.planner.validators.*."""

    def test_planner_rules_in_toolkit_slice(self):
        """Rules with planner.* archetype are in the PLANNED toolkit slice."""
        registry = [
            _make_toolkit_rule("planner.wagon.structure"),
            _make_toolkit_rule("planner.acceptance.criteria"),
            _make_toolkit_rule("planner.wmbt.consistency"),
            # Non-planner, non-acceptance-violation rules — excluded
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_toolkit_rule("tester.red.convention"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "planner.wagon.structure" in toolkit_ids
        assert "planner.acceptance.criteria" in toolkit_ids
        assert "planner.wmbt.consistency" in toolkit_ids

    def test_non_planner_non_substrate_rules_excluded(self):
        """Rules from other archetypes (not planner or acceptance-violation) are excluded."""
        registry = [
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_toolkit_rule("tester.red.convention"),
            _make_toolkit_rule("coach.rule-id-uniqueness"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert len(toolkit_ids) == 0


class TestPlannedToolkitMappingMatchesSection65:
    """AC-UNIT-002: PLANNED toolkit mapping matches the §6.5 table union."""

    def test_full_planned_toolkit_slice(self):
        """PLANNED = planner.* + tester.acceptance-violation.* — no other archetypes."""
        registry = [
            # planner rules
            _make_toolkit_rule("planner.wagon.structure"),
            _make_toolkit_rule("planner.acceptance.criteria"),
            # substrate enforcement rules
            _make_toolkit_rule("tester.acceptance-violation.acceptance-must-be-measurable"),
            _make_toolkit_rule("tester.acceptance-violation.acceptance-must-declare-phase"),
            _make_toolkit_rule("tester.acceptance-violation.disposition-must-not-be-declared"),
            _make_toolkit_rule("tester.acceptance-violation.validator-binding-must-be-bidirectional"),
            _make_toolkit_rule("tester.acceptance-violation.metric-implementation-must-exist"),
            # Excluded rules from other archetypes
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_toolkit_rule("tester.red.convention"),
            _make_toolkit_rule("coach.rule-id-uniqueness"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("PLANNED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        expected_ids = {
            "planner.wagon.structure",
            "planner.acceptance.criteria",
            "tester.acceptance-violation.acceptance-must-be-measurable",
            "tester.acceptance-violation.acceptance-must-declare-phase",
            "tester.acceptance-violation.disposition-must-not-be-declared",
            "tester.acceptance-violation.validator-binding-must-be-bidirectional",
            "tester.acceptance-violation.metric-implementation-must-exist",
        }
        assert toolkit_ids == expected_ids
