# URN: test:dispatch-validators:green-phase-selects-all-green-repo-rules
# Acceptance: acc:dispatch-validators:D001-UNIT-001-green-phase-selects-all-green-repo-rules
# WMBT: wmbt:dispatch-validators:D001
# Phase: GREEN
# Layer: domain

"""AC-UNIT-001: GREEN phase selects all GREEN repo rules + toolkit GREEN mapping.

Per spec §6.5: at GREEN, the selected set is:
  - Repo slice: every repo.* rule whose bind_rule(rule_id).phase == GREEN
  - Toolkit slice: atdd.coder.validators.* (coder.* archetype rules)
No repo rules with phase != GREEN are included.
"""

from pathlib import Path

import pytest

from atdd.coach.runtime.validator_selection import ValidatorSet, build_validator_set
from atdd.coach.utils.coach_config import CoachConfig, ValidatorsConfig
from atdd.coach.utils.rule_binding import RuleMetadata


_DUMMY_PATH = Path("/dev/null")


def _make_repo_rule(rule_id: str, phase: str, source_kind: str = "wmbt") -> RuleMetadata:
    """Create a repo RuleMetadata for testing."""
    return RuleMetadata(
        rule_id=rule_id,
        severity=4,
        description=f"test rule {rule_id}",
        recipe=None,
        introduced_in=None,
        source_path=_DUMMY_PATH,
        disposition="strict",
        phase=phase,
        acceptance_urn=f"acc:test-wagon:D001-UNIT-001-slug" if source_kind == "wmbt" else None,
        train_urn=f"train:test-train" if source_kind == "train" else None,
        security_urn=f"security:test-wagon:test-feature:001" if source_kind == "security" else None,
    )


def _make_toolkit_rule(rule_id: str, archetype: str) -> RuleMetadata:
    """Create a toolkit RuleMetadata for testing."""
    return RuleMetadata(
        rule_id=rule_id,
        severity=3,
        description=f"test toolkit rule {rule_id}",
        recipe=None,
        introduced_in=None,
        source_path=_DUMMY_PATH,
        disposition="strict",
    )


class TestGreenPhaseRepoRuleSelection:
    """AC-UNIT-001: GREEN selects all repo rules with phase=GREEN."""

    def test_green_repo_rules_from_all_source_kinds(self):
        """Repo rules with phase=GREEN from WMBT, train, and security are all included."""
        registry = [
            _make_repo_rule("repo.test-wagon.D001-acc-unit-001", "GREEN", "wmbt"),
            _make_repo_rule("repo.test-train.acc-green-check", "GREEN", "train"),
            _make_repo_rule("repo.test-wagon.test-feature-security-001", "GREEN", "security"),
            # Non-GREEN repo rules — must be excluded
            _make_repo_rule("repo.test-wagon.D001-acc-unit-002", "RED", "wmbt"),
            _make_repo_rule("repo.test-wagon.D001-acc-unit-003", "SMOKE", "wmbt"),
            _make_repo_rule("repo.test-wagon.D001-acc-unit-004", "PLANNED", "wmbt"),
            # Toolkit rules — should not appear in repo_slice
            _make_toolkit_rule("coder.dead-code.reachability", "coder"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        repo_ids = {r.rule_id for r in result.repo_slice}
        assert "repo.test-wagon.D001-acc-unit-001" in repo_ids
        assert "repo.test-train.acc-green-check" in repo_ids
        assert "repo.test-wagon.test-feature-security-001" in repo_ids

    def test_non_green_repo_rules_excluded(self):
        """Repo rules with phase != GREEN must not appear in repo_slice."""
        registry = [
            _make_repo_rule("repo.test-wagon.D001-acc-unit-010", "RED", "wmbt"),
            _make_repo_rule("repo.test-wagon.D001-acc-unit-011", "SMOKE", "wmbt"),
            _make_repo_rule("repo.test-wagon.D001-acc-unit-012", "PLANNED", "wmbt"),
            _make_repo_rule("repo.test-wagon.D001-acc-unit-013", "REFACTOR", "wmbt"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        assert len(result.repo_slice) == 0

    def test_repo_rules_without_phase_excluded(self):
        """Repo rules with phase=None must not appear in repo_slice."""
        registry = [
            RuleMetadata(
                rule_id="repo.test-wagon.D001-acc-unit-020",
                severity=4,
                description="no-phase rule",
                recipe=None,
                introduced_in=None,
                source_path=_DUMMY_PATH,
                disposition="strict",
                phase=None,
            ),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        assert len(result.repo_slice) == 0


class TestGreenPhaseToolkitSelection:
    """AC-UNIT-001: GREEN includes the toolkit GREEN mapping (coder.*)."""

    def test_coder_rules_in_toolkit_slice(self):
        """Rules with coder.* archetype are in the GREEN toolkit slice."""
        registry = [
            _make_toolkit_rule("coder.dead-code.reachability", "coder"),
            _make_toolkit_rule("coder.dto.testing-pattern", "coder"),
            _make_toolkit_rule("coder.error-response.compliance", "coder"),
            _make_toolkit_rule("coder.frontend.composition-root", "coder"),
            _make_toolkit_rule("coder.presentation.ratchet", "coder"),
            # Non-coder rules — should be excluded from GREEN toolkit
            _make_toolkit_rule("planner.wagon.structure", "planner"),
            _make_toolkit_rule("tester.red.convention", "tester"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "coder.dead-code.reachability" in toolkit_ids
        assert "coder.dto.testing-pattern" in toolkit_ids
        assert "coder.error-response.compliance" in toolkit_ids
        assert "coder.frontend.composition-root" in toolkit_ids
        assert "coder.presentation.ratchet" in toolkit_ids

    def test_non_coder_rules_excluded_from_green_toolkit(self):
        """Rules from other archetypes are excluded from GREEN toolkit slice."""
        registry = [
            _make_toolkit_rule("planner.wagon.structure", "planner"),
            _make_toolkit_rule("tester.red.convention", "tester"),
            _make_toolkit_rule("coach.rule-id-uniqueness", "coach"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert "planner.wagon.structure" not in toolkit_ids
        assert "tester.red.convention" not in toolkit_ids
        assert "coach.rule-id-uniqueness" not in toolkit_ids

    def test_repo_rules_not_in_toolkit_slice(self):
        """Repo rules never appear in the toolkit slice."""
        registry = [
            _make_repo_rule("repo.test-wagon.D001-acc-unit-001", "GREEN", "wmbt"),
            _make_toolkit_rule("coder.dead-code.reachability", "coder"),
        ]
        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        toolkit_ids = {r.rule_id for r in result.toolkit_slice}
        assert all(not rid.startswith("repo.") for rid in toolkit_ids)


class TestGreenPhaseUnion:
    """AC-UNIT-001: Selected set is the union of toolkit + repo slices."""

    def test_union_contains_both_slices(self):
        """all_rules property returns toolkit ∪ repo."""
        coder_rule = _make_toolkit_rule("coder.dead-code.reachability", "coder")
        repo_rule = _make_repo_rule("repo.test-wagon.D001-acc-unit-001", "GREEN", "wmbt")
        registry = [coder_rule, repo_rule]

        config = CoachConfig(validators=ValidatorsConfig(selection="default"))
        result = build_validator_set("GREEN", config, registry=registry)

        all_ids = {r.rule_id for r in result.all_rules}
        assert "coder.dead-code.reachability" in all_ids
        assert "repo.test-wagon.D001-acc-unit-001" in all_ids
