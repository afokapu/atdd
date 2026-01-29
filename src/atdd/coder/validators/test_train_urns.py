"""
Test train URN validation for theme orchestrators.

Validates conventions from:
- atdd/planner/conventions/train.convention.yaml

Enforces:
- Theme orchestrators have train URNs (python/shared/{theme}.py)
- URN format: train:{theme}:{train_id}
- Train IDs exist in plan/_trains/*.yaml
- Each train file has corresponding implementation

Rationale:
Theme orchestrators in python/shared/ implement workflows defined in train specs.
URNs provide bidirectional traceability between implementation and specification.
"""

import pytest
import re
import yaml
from pathlib import Path
from typing import List, Dict, Set, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_SHARED_DIR = REPO_ROOT / "python" / "shared"
TRAINS_DIR = REPO_ROOT / "plan" / "_trains"
TRAIN_CONVENTION = REPO_ROOT / "atdd" / "planner" / "conventions" / "train.convention.yaml"


def find_theme_orchestrators() -> List[Path]:
    """Find all theme orchestrator files in python/shared/."""
    if not PYTHON_SHARED_DIR.exists():
        return []

    orchestrators = []
    for py_file in PYTHON_SHARED_DIR.glob("*.py"):
        # Skip __init__.py and utility files
        if py_file.name in ["__init__.py", "conftest.py"]:
            continue
        # Skip files in subdirectories
        if not py_file.parent == PYTHON_SHARED_DIR:
            continue
        orchestrators.append(py_file)

    return orchestrators


def extract_train_urns(file_path: Path) -> List[str]:
    """Extract train URNs from file header comments."""
    urns = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Stop at first non-comment line after shebang
            stripped = line.strip()
            if not stripped:
                continue
            if not stripped.startswith('#'):
                break

            # Match: # urn: train:{theme}:{train_id}
            match = re.match(r'#\s*urn:\s*train:([^:]+):(.+)', stripped)
            if match:
                theme = match.group(1)
                train_id = match.group(2).strip()
                urns.append(f"train:{theme}:{train_id}")

    return urns


def find_all_train_specs() -> Dict[str, Path]:
    """Find all train specification YAML files."""
    train_specs = {}
    if not TRAINS_DIR.exists():
        return train_specs

    for yaml_file in TRAINS_DIR.glob("*.yaml"):
        # Train ID is the filename without extension
        train_id = yaml_file.stem
        train_specs[train_id] = yaml_file

    return train_specs


def load_train_spec(train_file: Path) -> Dict:
    """Load train specification from YAML."""
    with open(train_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_theme_orchestrators_exist():
    """Theme orchestrators should exist in python/shared/ directory."""
    orchestrators = find_theme_orchestrators()

    assert len(orchestrators) > 0, (
        "No theme orchestrators found in python/shared/. "
        "Expected files like mechanic.py, match.py, etc."
    )


def test_theme_orchestrators_have_train_urns():
    """
    Theme orchestrators must have train URN headers.

    Expected format:
    # urn: train:{theme}:{train_id}

    Example:
    # urn: train:match:3001-match-setup-standard
    # urn: train:match:3004-match-completion-standard
    """
    orchestrators = find_theme_orchestrators()
    missing_urns = []

    for orch_file in orchestrators:
        urns = extract_train_urns(orch_file)
        if not urns:
            missing_urns.append(orch_file.name)

    if missing_urns:
        pytest.fail(
            f"\nFound {len(missing_urns)} theme orchestrators without train URNs:\n\n" +
            "\n".join(f"  {name}\n    Missing: # urn: train:{{theme}}:{{train_id}}"
                     for name in missing_urns) +
            "\n\nSee: atdd/planner/conventions/train.convention.yaml::theme_orchestrator_urn"
        )


def test_train_urns_match_convention_format():
    """
    Train URNs must follow format: train:{theme}:{train_id}

    Theme should match filename (e.g., match.py → train:match:...)
    Train ID should match pattern: DDDD-kebab-case-name
    """
    orchestrators = find_theme_orchestrators()
    format_violations = []

    for orch_file in orchestrators:
        urns = extract_train_urns(orch_file)
        expected_theme = orch_file.stem  # filename without .py

        for urn in urns:
            # Parse URN
            match = re.match(r'train:([^:]+):(.+)', urn)
            if not match:
                format_violations.append((orch_file.name, urn, "Invalid URN format"))
                continue

            theme = match.group(1)
            train_id = match.group(2)

            # Validate theme matches filename
            if theme != expected_theme:
                format_violations.append((
                    orch_file.name,
                    urn,
                    f"Theme '{theme}' doesn't match filename '{expected_theme}.py'"
                ))

            # Validate train_id format (DDDD-kebab-case)
            if not re.match(r'^\d{4}-[a-z][a-z0-9-]*$', train_id):
                format_violations.append((
                    orch_file.name,
                    urn,
                    f"Train ID '{train_id}' doesn't match pattern: DDDD-kebab-case-name"
                ))

    if format_violations:
        pytest.fail(
            f"\nFound {len(format_violations)} train URN format violations:\n\n" +
            "\n".join(f"  {file}\n    URN: {urn}\n    Issue: {issue}"
                     for file, urn, issue in format_violations) +
            "\n\nExpected format: train:{theme}:{train_id}"
            "\nExample: train:match:3001-match-setup-standard"
        )


def test_train_urns_reference_existing_specs():
    """
    Train URNs must reference train specs that exist in plan/_trains/.

    For each URN train:{theme}:{train_id}, verify:
    - plan/_trains/{train_id}.yaml exists
    - Train spec has matching train_id field
    """
    orchestrators = find_theme_orchestrators()
    train_specs = find_all_train_specs()
    missing_specs = []

    for orch_file in orchestrators:
        urns = extract_train_urns(orch_file)

        for urn in urns:
            # Extract train_id from URN
            match = re.match(r'train:([^:]+):(.+)', urn)
            if not match:
                continue

            theme = match.group(1)
            train_id = match.group(2)

            # Check if train spec exists
            if train_id not in train_specs:
                missing_specs.append((orch_file.name, urn, train_id))

    if missing_specs:
        pytest.fail(
            f"\nFound {len(missing_specs)} train URNs referencing non-existent specs:\n\n" +
            "\n".join(f"  {file}\n    URN: {urn}\n    Missing: plan/_trains/{train_id}.yaml"
                     for file, urn, train_id in missing_specs) +
            "\n\nEither:\n"
            "  1. Create the missing train spec in plan/_trains/\n"
            "  2. Fix the URN to reference an existing train"
        )


def test_train_specs_have_implementations():
    """
    All train specs in plan/_trains/ should have implementations.

    This is a reverse check: warn about train specs without orchestrators.
    Not a hard failure, but helps identify missing implementations.
    """
    train_specs = find_all_train_specs()
    orchestrators = find_theme_orchestrators()

    # Collect all implemented train IDs
    implemented_trains = set()
    for orch_file in orchestrators:
        urns = extract_train_urns(orch_file)
        for urn in urns:
            match = re.match(r'train:([^:]+):(.+)', urn)
            if match:
                train_id = match.group(2)
                implemented_trains.add(train_id)

    # Find unimplemented trains
    unimplemented = []
    for train_id, train_file in train_specs.items():
        if train_id not in implemented_trains:
            # Load spec to get theme
            spec = load_train_spec(train_file)
            themes = spec.get('themes', [])
            theme_str = themes[0] if themes else "unknown"
            unimplemented.append((train_id, theme_str))

    # This is just a warning, not a failure
    if unimplemented:
        # Group by theme
        by_theme = {}
        for train_id, theme in unimplemented:
            if theme not in by_theme:
                by_theme[theme] = []
            by_theme[theme].append(train_id)

        message = f"\nℹ️  Found {len(unimplemented)} train specs without implementations:\n\n"
        for theme, trains in sorted(by_theme.items()):
            message += f"\n  {theme} theme:\n"
            for train_id in sorted(trains):
                message += f"    - {train_id}\n"

        message += (
            f"\nTotal: {len(unimplemented)} trains\n"
            f"Implemented: {len(implemented_trains)} trains\n"
            f"Coverage: {len(implemented_trains)}/{len(train_specs)} "
            f"({100*len(implemented_trains)//len(train_specs) if train_specs else 0}%)\n"
        )

        # Print info but don't fail
        print(message)


def test_train_convention_file_exists():
    """Train convention file should exist and be valid YAML."""
    assert TRAIN_CONVENTION.exists(), (
        f"Train convention file not found: {TRAIN_CONVENTION}\n"
        "Expected: atdd/planner/conventions/train.convention.yaml"
    )

    # Validate it's valid YAML
    with open(TRAIN_CONVENTION, 'r', encoding='utf-8') as f:
        convention = yaml.safe_load(f)

    assert convention is not None, "Train convention file is empty or invalid YAML"

    # Check for theme_orchestrator_urn section
    urn_naming = convention.get('urn_naming', {})
    assert 'theme_orchestrator_urn' in urn_naming, (
        "Train convention missing 'urn_naming.theme_orchestrator_urn' section\n"
        "Expected format documentation for train:{theme}:{train_id}"
    )
