"""
Tester validators: Train frontend E2E convention validation.

Train First-Class Spec v0.6 Section 7: Frontend E2E Conventions

Validates:
- SPEC-TRAIN-VAL-0026: Frontend E2E path convention
- SPEC-TRAIN-VAL-0027: Frontend E2E @train annotation
- SPEC-TRAIN-VAL-0028: Frontend E2E @see annotation

Frontend (web) E2E tests should follow:
- Path: web/e2e/<train_id>/*.spec.ts
- Annotation: @train <train_id>
- Docstring: @see plan/_trains/<train_id>.yaml
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
WEB_E2E_DIR = REPO_ROOT / "web" / "e2e"
TRAINS_DIR = REPO_ROOT / "plan" / "_trains"

# Package resources
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def _get_all_train_ids() -> List[str]:
    """
    Get all train IDs from the registry.

    Returns:
        List of train_id strings
    """
    import yaml

    train_ids = []
    trains_registry_path = REPO_ROOT / "plan" / "_trains.yaml"

    if trains_registry_path.exists():
        with open(trains_registry_path) as f:
            data = yaml.safe_load(f)

        for theme_key, categories in data.get("trains", {}).items():
            if isinstance(categories, dict):
                for category_key, trains_list in categories.items():
                    if isinstance(trains_list, list):
                        for train in trains_list:
                            train_id = train.get("train_id")
                            if train_id:
                                train_ids.append(train_id)

    return train_ids


def _find_frontend_e2e_tests() -> List[Tuple[Path, str]]:
    """
    Find all frontend E2E test files.

    Returns:
        List of (path, train_id_from_dirname) tuples
    """
    tests = []

    if not WEB_E2E_DIR.exists():
        return tests

    # Pattern: web/e2e/<train_id>/*.spec.ts
    for spec_file in WEB_E2E_DIR.rglob("*.spec.ts"):
        # Get train_id from parent directory
        parent_dir = spec_file.parent
        if parent_dir != WEB_E2E_DIR:
            train_id = parent_dir.name
            # Validate train_id pattern
            if re.match(r"^\d{4}-[a-z0-9-]+$", train_id):
                tests.append((spec_file, train_id))

    return tests


def _extract_train_annotations(file_path: Path) -> List[str]:
    """
    Extract @train annotations from a TypeScript test file.

    Returns:
        List of @train values
    """
    annotations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern: @train <train_id> in comments
        pattern = r'@train\s+([^\s\n\*]+)'
        matches = re.findall(pattern, content)
        annotations.extend(matches)

    except Exception:
        pass

    return annotations


def _extract_see_annotations(file_path: Path) -> List[str]:
    """
    Extract @see annotations from a TypeScript test file.

    Returns:
        List of @see values
    """
    see_annotations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern: @see <path> in comments
        pattern = r'@see\s+([^\s\n\*]+)'
        matches = re.findall(pattern, content)
        see_annotations.extend(matches)

    except Exception:
        pass

    return see_annotations


# ============================================================================
# FRONTEND E2E VALIDATORS
# ============================================================================


@pytest.mark.platform
def test_frontend_e2e_path_convention():
    """
    SPEC-TRAIN-VAL-0026: Frontend E2E path follows convention

    Given: Frontend E2E test files
    When: Checking file paths
    Then: Path follows web/e2e/<train_id>/*.spec.ts

    Section 7: Frontend E2E Path Convention
    """
    all_train_ids = set(_get_all_train_ids())

    if not all_train_ids:
        pytest.skip("No trains found in registry")

    if not WEB_E2E_DIR.exists():
        pytest.skip("No web/e2e/ directory found")

    violations = []
    e2e_tests = _find_frontend_e2e_tests()

    for test_path, train_id in e2e_tests:
        if train_id not in all_train_ids:
            rel_path = test_path.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}: directory '{train_id}' is not a registered train_id"
            )

    # Also check for spec files directly in web/e2e/ (no train_id directory)
    for spec_file in WEB_E2E_DIR.glob("*.spec.ts"):
        rel_path = spec_file.relative_to(REPO_ROOT)
        violations.append(
            f"{rel_path}: spec file should be in web/e2e/<train_id>/ subdirectory"
        )

    if violations:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Frontend E2E path violations:\n  " + "\n  ".join(violations) +
                "\n\nExpected: web/e2e/<train_id>/*.spec.ts"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0026",
                    violation,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_frontend_e2e_train_annotation():
    """
    SPEC-TRAIN-VAL-0027: Frontend E2E tests have @train annotation

    Given: Frontend E2E test files
    When: Checking for @train annotation
    Then: Tests have @train <train_id> in JSDoc comment

    Section 7: Frontend E2E @train Annotation
    """
    e2e_tests = _find_frontend_e2e_tests()

    if not e2e_tests:
        pytest.skip("No frontend E2E tests found")

    missing_annotation = []
    mismatched_annotation = []

    for test_path, train_id in e2e_tests:
        annotations = _extract_train_annotations(test_path)

        if not annotations:
            missing_annotation.append(
                f"{test_path.name}: no @train annotation"
            )
        elif train_id not in annotations:
            mismatched_annotation.append(
                f"{test_path.name}: expected @train {train_id} but found {annotations}"
            )

    violations = missing_annotation + mismatched_annotation

    if violations:
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Frontend E2E @train annotation issues:\n  " + "\n  ".join(violations) +
                "\n\nExpected: @train <train_id> in JSDoc comment"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0027",
                    violation,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )


@pytest.mark.platform
def test_frontend_e2e_see_annotation():
    """
    SPEC-TRAIN-VAL-0028: Frontend E2E tests have @see annotation

    Given: Frontend E2E test files
    When: Checking for @see annotation
    Then: Tests have @see plan/_trains/<train_id>.yaml annotation

    Section 7: Frontend E2E @see Annotation
    """
    e2e_tests = _find_frontend_e2e_tests()

    if not e2e_tests:
        pytest.skip("No frontend E2E tests found")

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
        if should_enforce(TrainSpecPhase.FULL_ENFORCEMENT):
            pytest.fail(
                f"Frontend E2E @see annotation issues:\n  " + "\n  ".join(violations) +
                "\n\nExpected: @see plan/_trains/<train_id>.yaml"
            )
        else:
            for violation in violations:
                emit_phase_warning(
                    "SPEC-TRAIN-VAL-0028",
                    violation,
                    TrainSpecPhase.FULL_ENFORCEMENT
                )
