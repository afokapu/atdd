"""
Coach validators: Train registry gap validation.

Train First-Class Spec v0.6 Section 14: Inventory Reporting

Validates:
- SPEC-TRAIN-VAL-0037: Inventory reports train gaps
- SPEC-TRAIN-VAL-0038: Gap report format validation

Ensures the inventory command properly reports gaps in train implementation
across backend, frontend, and frontend_python platforms.
"""

import pytest
from pathlib import Path
from typing import Dict, Any, List

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.commands.inventory import RepositoryInventory
from atdd.coach.utils.train_spec_phase import (
    TrainSpecPhase,
    should_enforce,
    emit_phase_warning
)


# Path constants
REPO_ROOT = find_repo_root()


@pytest.fixture(scope="module")
def train_inventory() -> Dict[str, Any]:
    """Generate train inventory with gap reporting."""
    inventory = RepositoryInventory(REPO_ROOT)
    return inventory.scan_trains()


@pytest.mark.platform
def test_inventory_reports_train_gaps(train_inventory):
    """
    SPEC-TRAIN-VAL-0037: Inventory reports train gaps

    Given: Inventory scan of trains
    When: Checking gap reporting fields
    Then: Inventory includes missing_test_* and missing_code_* arrays

    Section 14: Gap Reporting
    """
    required_gap_fields = [
        "missing_test_backend",
        "missing_test_frontend",
        "missing_test_frontend_python",
        "missing_code_backend",
        "missing_code_frontend",
        "missing_code_frontend_python"
    ]

    missing_fields = []
    for field in required_gap_fields:
        if field not in train_inventory:
            missing_fields.append(field)

    if missing_fields:
        pytest.fail(
            f"Inventory missing gap reporting fields:\n  " +
            "\n  ".join(missing_fields) +
            "\n\nExpected fields for Train First-Class Spec v0.6 Section 14"
        )

    # Verify all gap fields are lists
    for field in required_gap_fields:
        value = train_inventory.get(field)
        assert isinstance(value, list), \
            f"Gap field '{field}' should be a list, got {type(value).__name__}"


@pytest.mark.platform
def test_gap_report_format_validation(train_inventory):
    """
    SPEC-TRAIN-VAL-0038: Gap report format validation

    Given: Inventory with gap reporting
    When: Checking gap report structure
    Then: Gaps summary exists with correct format

    Section 14: Gap Report Format
    """
    # Check for gaps summary
    assert "gaps" in train_inventory, \
        "Inventory should include 'gaps' summary object"

    gaps = train_inventory["gaps"]

    # Validate structure
    assert isinstance(gaps, dict), \
        "gaps should be a dictionary"

    assert "test" in gaps, \
        "gaps should include 'test' category"

    assert "code" in gaps, \
        "gaps should include 'code' category"

    # Validate test gaps structure
    test_gaps = gaps["test"]
    assert isinstance(test_gaps, dict), \
        "gaps.test should be a dictionary"

    required_platforms = ["backend", "frontend", "frontend_python"]
    for platform in required_platforms:
        assert platform in test_gaps, \
            f"gaps.test should include '{platform}'"
        assert isinstance(test_gaps[platform], int), \
            f"gaps.test.{platform} should be an integer count"

    # Validate code gaps structure
    code_gaps = gaps["code"]
    assert isinstance(code_gaps, dict), \
        "gaps.code should be a dictionary"

    for platform in required_platforms:
        assert platform in code_gaps, \
            f"gaps.code should include '{platform}'"
        assert isinstance(code_gaps[platform], int), \
            f"gaps.code.{platform} should be an integer count"


@pytest.mark.platform
def test_gap_counts_match_arrays(train_inventory):
    """
    Verify gap counts match corresponding array lengths.

    Given: Inventory with gap reporting
    When: Comparing counts to arrays
    Then: Counts equal array lengths
    """
    gaps = train_inventory.get("gaps", {})

    # Test gaps
    test_gaps = gaps.get("test", {})
    assert test_gaps.get("backend", 0) == len(train_inventory.get("missing_test_backend", [])), \
        "gaps.test.backend count mismatch"
    assert test_gaps.get("frontend", 0) == len(train_inventory.get("missing_test_frontend", [])), \
        "gaps.test.frontend count mismatch"
    assert test_gaps.get("frontend_python", 0) == len(train_inventory.get("missing_test_frontend_python", [])), \
        "gaps.test.frontend_python count mismatch"

    # Code gaps
    code_gaps = gaps.get("code", {})
    assert code_gaps.get("backend", 0) == len(train_inventory.get("missing_code_backend", [])), \
        "gaps.code.backend count mismatch"
    assert code_gaps.get("frontend", 0) == len(train_inventory.get("missing_code_frontend", [])), \
        "gaps.code.frontend count mismatch"
    assert code_gaps.get("frontend_python", 0) == len(train_inventory.get("missing_code_frontend_python", [])), \
        "gaps.code.frontend_python count mismatch"


@pytest.mark.platform
def test_gap_train_ids_are_valid(train_inventory):
    """
    Verify train IDs in gap arrays are valid.

    Given: Inventory with gap arrays
    When: Checking train IDs
    Then: All train IDs in gaps are in train_ids list
    """
    all_train_ids = set(train_inventory.get("train_ids", []))

    if not all_train_ids:
        pytest.skip("No trains found in inventory")

    gap_fields = [
        "missing_test_backend",
        "missing_test_frontend",
        "missing_test_frontend_python",
        "missing_code_backend",
        "missing_code_frontend",
        "missing_code_frontend_python"
    ]

    invalid_ids = []
    for field in gap_fields:
        gap_ids = train_inventory.get(field, [])
        for train_id in gap_ids:
            if train_id not in all_train_ids:
                invalid_ids.append(f"{field}: {train_id}")

    assert not invalid_ids, \
        f"Gap arrays contain invalid train IDs:\n  " + "\n  ".join(invalid_ids)
