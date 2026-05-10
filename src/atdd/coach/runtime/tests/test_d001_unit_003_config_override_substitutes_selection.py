# URN: test:dispatch-validators:config-override-substitutes-selection
# Acceptance: acc:dispatch-validators:D001-UNIT-003-config-override-substitutes-selection
# WMBT: wmbt:dispatch-validators:D001
# Phase: GREEN
# Layer: domain

"""AC-UNIT-003: Config override substitutes the toolkit slice per phase.

Per spec §6.5 override semantics:
  - Override sets the toolkit slice for the named phase (exhaustive — defaults
    are NOT additionally unioned in for that phase).
  - Override does NOT change the repo-rule slice (still computed from
    bind_rule(rule_id).phase per substrate v12).
  - Phases not present in the override fall back to the §6.5 default mapping.
"""

from pathlib import Path

import pytest

from atdd.coach.runtime.validator_selection import ValidatorSet, build_validator_set
from atdd.coach.utils.coach_config import CoachConfig, ValidatorsConfig
from atdd.coach.utils.rule_binding import RuleMetadata


_DUMMY_PATH = Path("/dev/null")


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


def _make_repo_rule(rule_id: str, phase: str) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        severity=4,
        description=f"test repo {rule_id}",
        recipe=None,
        introduced_in=None,
        source_path=_DUMMY_PATH,
        disposition="strict",
        phase=phase,
    )


class TestConfigOverrideToolkitSlice:
    """AC-UNIT-003: Override substitutes the toolkit slice exhaustively."""

    def test_override_replaces_default_toolkit_slice(self):
        """When override is set for GREEN, toolkit slice equals override list only."""
        registry = [
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_toolkit_rule("coder.dto.testing-pattern"),
            _make_toolkit_rule("coder.error-response.compliance"),
            _make_toolkit_rule("planner.wagon.structure"),
            _make_repo_rule("repo.test.D001-acc-unit-001", "GREEN"),
        ]
        # Override GREEN to only include dead-code — dto and error-response excluded
        config = CoachConfig(
            validators=ValidatorsConfig(
                selection={"GREEN": ["coder.dead-code.reachability"]}
            )
        )
        result = build_validator_set("GREEN", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert toolkit_ids == {"coder.dead-code.reachability"}
        assert "coder.dto.testing-pattern" not in toolkit_ids
        assert "coder.error-response.compliance" not in toolkit_ids

    def test_defaults_not_unioned_into_overridden_phase(self):
        """Defaults are NOT additionally unioned in for the overridden phase."""
        registry = [
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_toolkit_rule("coder.dto.testing-pattern"),
        ]
        # Override GREEN to only include dead-code
        config = CoachConfig(
            validators=ValidatorsConfig(
                selection={"GREEN": ["coder.dead-code.reachability"]}
            )
        )
        result = build_validator_set("GREEN", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        # dto.testing-pattern is in the default GREEN mapping but NOT in override
        assert "coder.dto.testing-pattern" not in toolkit_ids


class TestConfigOverrideRepoSliceUnaffected:
    """AC-UNIT-003: Repo-rule slice is unaffected by override."""

    def test_repo_slice_still_computed_from_phase(self):
        """Repo slice still derives from bind_rule(rule_id).phase, not override."""
        registry = [
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_repo_rule("repo.test.D001-acc-unit-001", "GREEN"),
            _make_repo_rule("repo.test.D001-acc-unit-002", "RED"),
        ]
        config = CoachConfig(
            validators=ValidatorsConfig(
                selection={"GREEN": ["coder.dead-code.reachability"]}
            )
        )
        result = build_validator_set("GREEN", config, registry=registry)

        repo_ids = {r.rule_id for r in result.repo_slice}
        assert "repo.test.D001-acc-unit-001" in repo_ids
        assert "repo.test.D001-acc-unit-002" not in repo_ids

    def test_override_does_not_filter_repo_rules(self):
        """Override only affects toolkit slice; repo rules are independent."""
        green_repo = _make_repo_rule("repo.test.D001-acc-unit-001", "GREEN")
        registry = [
            _make_toolkit_rule("planner.wagon.structure"),  # not in GREEN default or override
            green_repo,
        ]
        # Override GREEN to empty list — toolkit slice is empty, but repo is unaffected
        config = CoachConfig(
            validators=ValidatorsConfig(
                selection={"GREEN": []}
            )
        )
        result = build_validator_set("GREEN", config, registry=registry)

        assert len(result.toolkit_slice) == 0
        assert len(result.repo_slice) == 1
        assert result.repo_slice[0].rule_id == "repo.test.D001-acc-unit-001"


class TestConfigOverrideFallbackForUnspecifiedPhases:
    """AC-UNIT-003: Phases not in override fall back to §6.5 defaults."""

    def test_unspecified_phase_uses_default_mapping(self):
        """RED phase uses §6.5 defaults when only GREEN is overridden."""
        registry = [
            _make_toolkit_rule("tester.red.convention"),
            _make_toolkit_rule("tester.filename.naming"),
            _make_toolkit_rule("coder.dead-code.reachability"),
        ]
        # Override GREEN only — RED should use defaults (tester.*)
        config = CoachConfig(
            validators=ValidatorsConfig(
                selection={"GREEN": ["coder.dead-code.reachability"]}
            )
        )
        result = build_validator_set("RED", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "tester.red.convention" in toolkit_ids
        assert "tester.filename.naming" in toolkit_ids
        # coder rules are NOT in RED default mapping
        assert "coder.dead-code.reachability" not in toolkit_ids

    def test_string_default_uses_section65_mapping(self):
        """selection='default' (string) uses §6.5 mapping for all phases."""
        registry = [
            _make_toolkit_rule("coder.dead-code.reachability"),
            _make_toolkit_rule("planner.wagon.structure"),
        ]
        config = CoachConfig(
            validators=ValidatorsConfig(selection="default")
        )
        green_result = build_validator_set("GREEN", config, registry=registry)
        planned_result = build_validator_set("PLANNED", config, registry=registry)

        green_ids = {r.rule_id for r in green_result.toolkit_slice}
        planned_ids = {r.rule_id for r in planned_result.toolkit_slice}

        assert "coder.dead-code.reachability" in green_ids
        assert "planner.wagon.structure" in planned_ids
        assert "coder.dead-code.reachability" not in planned_ids
