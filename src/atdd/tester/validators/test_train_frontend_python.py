"""
Tester validators: Train frontend Python (Streamlit) convention validation.

Train First-Class Spec v0.6 Section 8: Frontend Python Conventions

Validates:
- SPEC-TRAIN-VAL-0029: Frontend Python code paths
- SPEC-TRAIN-VAL-0030: Frontend Python test paths

Frontend Python (Streamlit) should follow:
- Code paths: python/streamlit/ or python/apps/
- Test paths: python/tests/streamlit/test_<train_id>[_<slug>].py
"""

import pytest
import re
from pathlib import Path
from typing import Dict, List, Tuple

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.train_spec_phase import (
    TrainSpecPhase,
    should_enforce,
    emit_phase_warning
)


# Path constants
REPO_ROOT = find_repo_root()
PYTHON_DIR = REPO_ROOT / "python"
STREAMLIT_DIR = PYTHON_DIR / "streamlit"
APPS_DIR = PYTHON_DIR / "apps"
STREAMLIT_TESTS_DIR = PYTHON_DIR / "tests" / "streamlit"

# Package resources
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def _get_trains_with_frontend_python() -> List[str]:
    """
    Get train IDs that expect frontend_python implementation.

    Returns:
        List of train_id strings
    """
    import yaml

    train_ids = []
    trains_registry_path = REPO_ROOT / "plan" / "_trains.yaml"

    if not trains_registry_path.exists():
        return train_ids

    with open(trains_registry_path) as f:
        data = yaml.safe_load(f)

    trains_dir = REPO_ROOT / "plan" / "_trains"

    for theme_key, categories in data.get("trains", {}).items():
        if isinstance(categories, dict):
            for category_key, trains_list in categories.items():
                if isinstance(trains_list, list):
                    for train in trains_list:
                        train_id = train.get("train_id")
                        if not train_id:
                            continue

                        # Check expectations in registry
                        expectations = train.get("expectations", {})
                        if expectations.get("frontend_python"):
                            train_ids.append(train_id)
                            continue

                        # Check YAML file for expectations
                        train_file = trains_dir / f"{train_id}.yaml"
                        if train_file.exists():
                            try:
                                with open(train_file) as tf:
                                    train_data = yaml.safe_load(tf)
                                yaml_expectations = train_data.get("expectations", {})
                                if yaml_expectations.get("frontend_python"):
                                    train_ids.append(train_id)
                            except Exception:
                                pass

    return train_ids


def _find_frontend_python_code_files() -> List[Path]:
    """
    Find all frontend Python code files.

    Returns:
        List of paths to .py files in streamlit/ or apps/ directories
    """
    files = []

    for search_dir in [STREAMLIT_DIR, APPS_DIR]:
        if search_dir.exists():
            for py_file in search_dir.rglob("*.py"):
                if not py_file.name.startswith("_"):
                    files.append(py_file)

    return files


def _find_frontend_python_test_files() -> List[Tuple[Path, str]]:
    """
    Find all frontend Python test files.

    Returns:
        List of (path, train_id_from_filename) tuples
    """
    tests = []

    if not STREAMLIT_TESTS_DIR.exists():
        return tests

    # Pattern: test_<train_id>*.py
    for test_file in STREAMLIT_TESTS_DIR.glob("test_*.py"):
        filename = test_file.stem
        match = re.match(r"test_(\d{4}-[a-z0-9-]+)", filename)
        if match:
            train_id = match.group(1)
            tests.append((test_file, train_id))

    return tests


def _check_train_code_references(train_id: str) -> List[Path]:
    """
    Find code files that reference a specific train.

    Returns:
        List of paths that contain train_id reference
    """
    matching_files = []

    for search_dir in [STREAMLIT_DIR, APPS_DIR]:
        if not search_dir.exists():
            continue

        for py_file in search_dir.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Check for train_id in file
                if train_id in content:
                    matching_files.append(py_file)

            except Exception:
                pass

    return matching_files


# ============================================================================
# FRONTEND PYTHON VALIDATORS
# ============================================================================


@pytest.mark.platform
def test_frontend_python_code_paths():
    """
    SPEC-TRAIN-VAL-0029: Frontend Python code in allowed paths

    Given: Trains expecting frontend_python implementation
    When: Checking code locations
    Then: Code is in python/streamlit/ or python/apps/

    Section 8: Frontend Python Code Paths
    """
    trains_with_frontend_python = _get_trains_with_frontend_python()

    if not trains_with_frontend_python:
        pytest.skip("No trains expecting frontend_python implementation")

    code_files = _find_frontend_python_code_files()

    if not code_files:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Trains expect frontend_python but no code found in python/streamlit/ or python/apps/:\n"
                f"  Trains: {trains_with_frontend_python}"
            )
        else:
            emit_phase_warning(
                "SPEC-TRAIN-VAL-0029",
                f"{len(trains_with_frontend_python)} trains expect frontend_python but no code found",
                TrainSpecPhase.FULL_ENFORCEMENT
            )
        return

    # Check that trains with expectations have corresponding code
    missing_code = []
    for train_id in trains_with_frontend_python:
        refs = _check_train_code_references(train_id)
        if not refs:
            missing_code.append(f"{train_id}: no code references found")

    if missing_code:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Trains missing frontend_python code:\n  " + "\n  ".join(missing_code) +
                "\n\nExpected code in: python/streamlit/ or python/apps/"
            )
        else:
            for missing in missing_code:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0029",
                    missing,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_frontend_python_test_paths():
    """
    SPEC-TRAIN-VAL-0030: Frontend Python tests in correct location

    Given: Frontend Python test files
    When: Checking test paths
    Then: Path follows python/tests/streamlit/test_<train_id>[_<slug>].py

    Section 8: Frontend Python Test Paths
    """
    trains_with_frontend_python = _get_trains_with_frontend_python()

    if not trains_with_frontend_python:
        pytest.skip("No trains expecting frontend_python implementation")

    test_files = _find_frontend_python_test_files()

    # Check that tests exist for trains that expect frontend_python
    train_ids_with_tests = {train_id for _, train_id in test_files}

    missing_tests = []
    for train_id in trains_with_frontend_python:
        if train_id not in train_ids_with_tests:
            missing_tests.append(
                f"{train_id}: missing test at python/tests/streamlit/test_{train_id}.py"
            )

    if missing_tests:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Trains missing frontend_python tests:\n  " + "\n  ".join(missing_tests) +
                "\n\nExpected: python/tests/streamlit/test_<train_id>[_<slug>].py"
            )
        else:
            for missing in missing_tests:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0030",
                    missing,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )

    # Validate existing test file naming
    invalid_tests = []
    all_train_ids = set(trains_with_frontend_python)

    for test_path, train_id in test_files:
        if train_id not in all_train_ids:
            rel_path = test_path.relative_to(REPO_ROOT)
            invalid_tests.append(
                f"{rel_path}: train_id '{train_id}' not in trains expecting frontend_python"
            )

    if invalid_tests:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Frontend Python test path issues:\n  " + "\n  ".join(invalid_tests)
            )
        else:
            for invalid in invalid_tests:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0030",
                    invalid,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )
