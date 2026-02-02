"""
Tester validators: Train backend E2E convention validation.

Train First-Class Spec v0.6 Section 6: Backend E2E Conventions

Validates:
- SPEC-TRAIN-VAL-0022: Backend E2E path convention
- SPEC-TRAIN-VAL-0023: Backend E2E pytest markers
- SPEC-TRAIN-VAL-0024: Backend E2E @see annotation
- SPEC-TRAIN-VAL-0025: Runner evidence detection

Backend E2E tests should follow:
- Path: e2e/<theme>/test_<train_id>[_<slug>].py
- Marker: @pytest.mark.train("<train_id>")
- Docstring: @see plan/_trains/<train_id>.yaml
- Runner: Use TrainRunner or train_runner fixture
"""

import pytest
import re
import ast
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.train_spec_phase import (
    TrainSpecPhase,
    should_enforce,
    emit_phase_warning
)


# Path constants
REPO_ROOT = find_repo_root()
E2E_DIR = REPO_ROOT / "e2e"
TRAINS_DIR = REPO_ROOT / "plan" / "_trains"

# Package resources
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def _get_all_train_ids() -> Dict[str, str]:
    """
    Get all train IDs mapped to their themes.

    Returns:
        Dict mapping train_id -> theme
    """
    import yaml

    train_to_theme = {}
    trains_registry_path = REPO_ROOT / "plan" / "_trains.yaml"

    if trains_registry_path.exists():
        with open(trains_registry_path) as f:
            data = yaml.safe_load(f)

        for theme_key, categories in data.get("trains", {}).items():
            theme = theme_key.split("-", 1)[1] if "-" in theme_key else theme_key
            if isinstance(categories, dict):
                for category_key, trains_list in categories.items():
                    if isinstance(trains_list, list):
                        for train in trains_list:
                            train_id = train.get("train_id")
                            if train_id:
                                train_to_theme[train_id] = theme

    return train_to_theme


def _find_backend_e2e_tests() -> List[Tuple[Path, str]]:
    """
    Find all backend E2E test files.

    Returns:
        List of (path, train_id_from_filename) tuples
    """
    tests = []

    if not E2E_DIR.exists():
        return tests

    # Pattern: e2e/<theme>/test_<train_id>*.py
    for test_file in E2E_DIR.rglob("test_*.py"):
        # Extract train_id from filename
        filename = test_file.stem  # e.g., test_0001-auth-session
        match = re.match(r"test_(\d{4}-[a-z0-9-]+)", filename)
        if match:
            train_id = match.group(1)
            tests.append((test_file, train_id))

    return tests


def _extract_pytest_markers(file_path: Path) -> List[str]:
    """
    Extract pytest marker values from a test file.

    Returns:
        List of @pytest.mark.train("<value>") values
    """
    markers = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern: @pytest.mark.train("...")
        pattern = r'@pytest\.mark\.train\(["\']([^"\']+)["\']\)'
        matches = re.findall(pattern, content)
        markers.extend(matches)

    except Exception:
        pass

    return markers


def _extract_see_annotations(file_path: Path) -> List[str]:
    """
    Extract @see annotations from docstrings.

    Returns:
        List of @see values
    """
    see_annotations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern: @see <path> in docstrings
        pattern = r'@see\s+([^\s\n]+)'
        matches = re.findall(pattern, content)
        see_annotations.extend(matches)

    except Exception:
        pass

    return see_annotations


def _detect_runner_evidence(file_path: Path) -> Dict[str, bool]:
    """
    Detect TrainRunner usage evidence in a test file.

    Returns:
        Dict with evidence flags: fixture, import, call
    """
    evidence = {
        "fixture": False,
        "import": False,
        "call": False
    }

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for fixture usage
        if "train_runner" in content or "TrainRunner" in content:
            # Fixture pattern: def test_xxx(train_runner):
            if re.search(r'def\s+test_\w+\s*\([^)]*train_runner', content):
                evidence["fixture"] = True

            # Import pattern
            if re.search(r'from\s+[\w.]+\s+import\s+[^;]*TrainRunner', content):
                evidence["import"] = True

            # Call pattern: runner.execute() or train_runner.execute()
            if re.search(r'\w+\.execute\s*\(', content):
                evidence["call"] = True

    except Exception:
        pass

    return evidence


# ============================================================================
# BACKEND E2E VALIDATORS
# ============================================================================


@pytest.mark.platform
def test_backend_e2e_path_convention():
    """
    SPEC-TRAIN-VAL-0022: Backend E2E path follows convention

    Given: Backend E2E test files
    When: Checking file paths
    Then: Path follows e2e/<theme>/test_<train_id>[_<slug>].py

    Section 6: Backend E2E Path Convention
    """
    train_to_theme = _get_all_train_ids()

    if not train_to_theme:
        pytest.skip("No trains found in registry")

    violations = []
    e2e_tests = _find_backend_e2e_tests()

    for test_path, train_id in e2e_tests:
        if train_id not in train_to_theme:
            continue

        expected_theme = train_to_theme[train_id]
        rel_path = test_path.relative_to(REPO_ROOT)

        # Check if theme is in path
        path_parts = rel_path.parts
        if len(path_parts) >= 2:
            actual_theme = path_parts[1]  # e2e/<theme>/test_xxx.py
            if actual_theme != expected_theme:
                violations.append(
                    f"{rel_path}: expected theme '{expected_theme}' but found '{actual_theme}'"
                )

    if violations:
        if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
            pytest.fail(
                f"Backend E2E path violations:\n  " + "\n  ".join(violations) +
                "\n\nExpected: e2e/<theme>/test_<train_id>[_<slug>].py"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0022",
                    violation,
                    TrainSpecPhase.BACKEND_ENFORCEMENT
                )


@pytest.mark.platform
def test_backend_e2e_pytest_markers():
    """
    SPEC-TRAIN-VAL-0023: Backend E2E tests have @pytest.mark.train marker

    Given: Backend E2E test files
    When: Checking pytest markers
    Then: Tests have @pytest.mark.train("<train_id>") decorator

    Section 6: Backend E2E Markers
    """
    e2e_tests = _find_backend_e2e_tests()

    if not e2e_tests:
        pytest.skip("No backend E2E tests found")

    missing_markers = []
    mismatched_markers = []

    for test_path, train_id in e2e_tests:
        markers = _extract_pytest_markers(test_path)

        if not markers:
            missing_markers.append(f"{test_path.name}: no @pytest.mark.train marker")
        elif train_id not in markers:
            mismatched_markers.append(
                f"{test_path.name}: expected train_id '{train_id}' but found {markers}"
            )

    violations = missing_markers + mismatched_markers

    if violations:
        if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
            pytest.fail(
                f"Backend E2E marker issues:\n  " + "\n  ".join(violations) +
                "\n\nExpected: @pytest.mark.train(\"<train_id>\")"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0023",
                    violation,
                    TrainSpecPhase.BACKEND_ENFORCEMENT
                )


@pytest.mark.platform
def test_backend_e2e_see_annotation():
    """
    SPEC-TRAIN-VAL-0024: Backend E2E tests have @see annotation in docstring

    Given: Backend E2E test files
    When: Checking docstrings
    Then: Tests have @see plan/_trains/<train_id>.yaml annotation

    Section 6: Backend E2E @see Annotation
    """
    e2e_tests = _find_backend_e2e_tests()

    if not e2e_tests:
        pytest.skip("No backend E2E tests found")

    missing_see = []
    invalid_see = []

    for test_path, train_id in e2e_tests:
        see_annotations = _extract_see_annotations(test_path)

        if not see_annotations:
            missing_see.append(f"{test_path.name}: no @see annotation")
        else:
            # Check for valid train reference
            expected_ref = f"plan/_trains/{train_id}.yaml"
            has_valid_ref = any(expected_ref in see for see in see_annotations)
            if not has_valid_ref:
                invalid_see.append(
                    f"{test_path.name}: expected @see {expected_ref}"
                )

    violations = missing_see + invalid_see

    if violations:
        if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
            pytest.fail(
                f"Backend E2E @see annotation issues:\n  " + "\n  ".join(violations) +
                "\n\nExpected: @see plan/_trains/<train_id>.yaml"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0024",
                    violation,
                    TrainSpecPhase.BACKEND_ENFORCEMENT
                )


@pytest.mark.platform
def test_backend_e2e_runner_evidence():
    """
    SPEC-TRAIN-VAL-0025: Backend E2E tests have runner evidence

    Given: Backend E2E test files
    When: Checking for TrainRunner usage
    Then: Tests have fixture, import, or call evidence of runner usage

    Section 6: Runner Evidence Detection
    """
    e2e_tests = _find_backend_e2e_tests()

    if not e2e_tests:
        pytest.skip("No backend E2E tests found")

    no_evidence = []

    for test_path, train_id in e2e_tests:
        evidence = _detect_runner_evidence(test_path)

        has_any_evidence = evidence["fixture"] or evidence["import"] or evidence["call"]
        if not has_any_evidence:
            no_evidence.append(
                f"{test_path.name}: no TrainRunner evidence found"
            )

    if no_evidence:
        if should_enforce(TrainSpecPhase.BACKEND_ENFORCEMENT):
            pytest.fail(
                f"Backend E2E tests missing runner evidence:\n  " + "\n  ".join(no_evidence) +
                "\n\nExpected: train_runner fixture, TrainRunner import, or .execute() call"
            )
        else:
            for missing in no_evidence:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0025",
                    missing,
                    TrainSpecPhase.BACKEND_ENFORCEMENT
                )
