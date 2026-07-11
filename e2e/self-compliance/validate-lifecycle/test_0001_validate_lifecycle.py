# URN: test:train:0001-self-compliance-validate:E2E-001-validate-lifecycle
# Train: train:0001-self-compliance-validate
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: Validate the self-compliance lifecycle: plan artifacts exist, validators run, gate passes
"""
Journey test for train:0001-self-compliance-validate
train: 0001-self-compliance-validate | phase: GREEN
Purpose: Validate the ATDD self-compliance lifecycle end-to-end via artifact inspection
"""

import pytest
import yaml
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()


# ============================================================================
# Step 1: Planner — wagon manifests and train definition exist
# ============================================================================

class TestStep1PlannerArtifacts:
    """Verify planner phase produced required plan artifacts."""

    def test_trains_file_exists(self):
        """plan/_trains.yaml must exist and define at least one train."""
        trains_file = REPO_ROOT / "plan" / "_trains.yaml"
        assert trains_file.exists(), f"Missing: {trains_file}"
        data = yaml.safe_load(trains_file.read_text())
        assert data.get("trains"), "plan/_trains.yaml has no trains defined"

    def test_wagons_file_exists(self):
        """plan/_wagons.yaml must exist and define at least one wagon."""
        wagons_file = REPO_ROOT / "plan" / "_wagons.yaml"
        assert wagons_file.exists(), f"Missing: {wagons_file}"
        data = yaml.safe_load(wagons_file.read_text())
        assert data.get("wagons"), "plan/_wagons.yaml has no wagons defined"

    def test_train_0001_definition(self):
        """Train 0001-self-compliance-validate must be fully defined."""
        train_file = REPO_ROOT / "plan" / "_trains" / "0001-self-compliance-validate.yaml"
        assert train_file.exists(), f"Missing: {train_file}"
        data = yaml.safe_load(train_file.read_text())
        assert data["train_id"] == "0001-self-compliance-validate"
        assert len(data.get("sequence", [])) >= 4, "Train must have at least 4 steps"
        assert len(data.get("participants", [])) >= 4, "Train must have at least 4 participants"

    def test_wagon_manifests_exist(self):
        """Each participant wagon must have a manifest in plan/."""
        train_file = REPO_ROOT / "plan" / "_trains" / "0001-self-compliance-validate.yaml"
        data = yaml.safe_load(train_file.read_text())
        plan_dir = REPO_ROOT / "plan"
        for participant in data.get("participants", []):
            if participant.startswith("wagon:"):
                wagon_slug = participant.split(":", 1)[1]
                wagon_dir = plan_dir / wagon_slug.replace("-", "_")
                assert wagon_dir.exists(), (
                    f"Wagon directory missing for {participant}: {wagon_dir}"
                )


# ============================================================================
# Step 2: Tester — validators exist for each phase
# ============================================================================

class TestStep2TesterArtifacts:
    """Verify tester phase validators are present."""

    @pytest.mark.parametrize("phase", ["planner", "tester", "coder", "coach"])
    def test_validator_directory_exists(self, phase):
        """Each ATDD phase must have a validators directory."""
        import atdd
        pkg_dir = Path(atdd.__file__).resolve().parent
        validators_dir = pkg_dir / phase / "validators"
        assert validators_dir.exists(), f"Missing validators: {validators_dir}"

    @pytest.mark.parametrize("phase", ["planner", "tester", "coder", "coach"])
    def test_validators_not_empty(self, phase):
        """Each phase must have at least one validator test file."""
        import atdd
        pkg_dir = Path(atdd.__file__).resolve().parent
        validators_dir = pkg_dir / phase / "validators"
        test_files = list(validators_dir.glob("test_*.py"))
        assert len(test_files) > 0, f"No test_*.py files in {validators_dir}"


# ============================================================================
# Step 3: Coder — implementation code exists
# ============================================================================

class TestStep3CoderArtifacts:
    """Verify coder phase produced implementation code."""

    def test_cli_module_exists(self):
        """The CLI entry point must be importable."""
        from atdd.cli import main
        assert callable(main)

    def test_coach_commands_exist(self):
        """Core coach commands must be importable."""
        from atdd.coach.commands.issue import IssueManager
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        from atdd.coach.commands.gate import ATDDGate
        from atdd.coach.commands.test_runner import TestRunner
        assert all([IssueManager, IssueLifecycle, ATDDGate, TestRunner])


# ============================================================================
# Step 4: Coach — gate verification works
# ============================================================================

class TestStep4CoachGate:
    """Verify coach gate can verify loaded rules."""

    def test_gate_module_importable(self):
        """ATDDGate must be importable and instantiable."""
        from atdd.coach.commands.gate import ATDDGate
        gate = ATDDGate()
        assert gate is not None

    def test_conventions_exist(self):
        """Smoke convention (and others) must exist in the package."""
        import atdd
        pkg_dir = Path(atdd.__file__).resolve().parent
        smoke_conv = pkg_dir / "tester" / "conventions" / "smoke.convention.yaml"
        assert smoke_conv.exists(), f"Missing: {smoke_conv}"
        red_conv = pkg_dir / "tester" / "conventions" / "red.convention.yaml"
        assert red_conv.exists(), f"Missing: {red_conv}"
