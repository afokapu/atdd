"""
Test WMBT files use authorized vocabulary from convention.

Validates that WMBT YAML files use only authorized terms defined in:
- .claude/conventions/planner/wmbt.convention.yaml
- .claude/schemas/planner/wmbt.schema.json

Enforces:
- Authorized step codes (D, L, P, C, E, M, Y, R, K)
- Authorized directions (minimize, maximize, increase, decrease)
- Authorized dimensions (time, effort, likelihood, frequency, quantity, financial value)
- Authorized lens patterns (functional.*, emotional.*, social.*)
- Statement construction follows pattern: {direction} {dimension} of {object_of_control} {context_clarifier}

Rationale:
Controlled vocabulary ensures consistency, traceability, and proper interpretation
of WMBT statements across the entire platform.
"""

import pytest
import yaml
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = REPO_ROOT / "plan"
WMBT_CONVENTION = REPO_ROOT / "atdd" / "planner" / "conventions" / "wmbt.convention.yaml"


# Authorized vocabulary from convention
AUTHORIZED_STEPS = {
    "define": "D",
    "locate": "L",
    "prepare": "P",
    "confirm": "C",
    "execute": "E",
    "monitor": "M",
    "modify": "Y",
    "resolve": "R",
    "conclude": "K",
}

STEP_CODES = set(AUTHORIZED_STEPS.values())

AUTHORIZED_DIRECTIONS = {
    "minimize",
    "maximize",
    "increase",
    "decrease",
}

AUTHORIZED_DIMENSIONS = {
    "time",
    "effort",
    "likelihood",
    "frequency",
    "quantity",
    "financial value",
}

AUTHORIZED_LENS_CATEGORIES = {
    "functional",
    "emotional",
    "social",
}

# Specific authorized lens attributes from convention
AUTHORIZED_FUNCTIONAL_LENSES = {
    "efficiency",
    "effectiveness",
    "availability",
    "adaptability",
    "sustainability",
}

AUTHORIZED_EMOTIONAL_LENSES = {
    "joy",
    "trust",
    "fear",
    "surprise",
    "sadness",
    "disgust",
    "anger",
    "anticipation",
}

AUTHORIZED_SOCIAL_LENSES = {
    "belong",
    "stand_out",
    "affirm",
    "aspire",
}


def find_wmbt_files() -> List[Tuple[str, Path]]:
    """
    Find all WMBT YAML files in plan/{wagon}/ directories.

    Returns: List[(wagon_slug, wmbt_file_path)]
    """
    wmbt_files = []

    if not PLAN_DIR.exists():
        return wmbt_files

    for wagon_dir in PLAN_DIR.iterdir():
        if not wagon_dir.is_dir():
            continue

        # Directory name uses underscores, convert to kebab-case slug
        dir_name = wagon_dir.name
        wagon_slug = dir_name.replace("_", "-")

        # Find all WMBT files matching pattern: {STEP_CODE}{NNN}.yaml
        for yaml_file in wagon_dir.glob("*.yaml"):
            filename = yaml_file.stem

            # Check if it matches WMBT pattern
            if len(filename) == 4 and filename[0] in STEP_CODES and filename[1:].isdigit():
                wmbt_files.append((wagon_slug, yaml_file))

    return wmbt_files


def load_wmbt_file(file_path: Path) -> Optional[Dict]:
    """Load and parse WMBT YAML file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def validate_step(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate step field uses authorized vocabulary.

    Returns: Error message if invalid, None if valid
    """
    step = wmbt_data.get("step")

    if not step:
        return f"Missing required field 'step'"

    if step not in AUTHORIZED_STEPS:
        return (
            f"Step '{step}' is not authorized. "
            f"Must be one of: {', '.join(sorted(AUTHORIZED_STEPS.keys()))}"
        )

    return None


def validate_direction(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate direction field uses authorized vocabulary.

    Returns: Error message if invalid, None if valid
    """
    direction = wmbt_data.get("direction")

    if not direction:
        return f"Missing required field 'direction'"

    if direction not in AUTHORIZED_DIRECTIONS:
        return (
            f"Direction '{direction}' is not authorized. "
            f"Must be one of: {', '.join(sorted(AUTHORIZED_DIRECTIONS))}"
        )

    return None


def validate_dimension(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate dimension field uses authorized vocabulary.

    Returns: Error message if invalid, None if valid
    """
    dimension = wmbt_data.get("dimension")

    if not dimension:
        return f"Missing required field 'dimension'"

    if dimension not in AUTHORIZED_DIMENSIONS:
        return (
            f"Dimension '{dimension}' is not authorized. "
            f"Must be one of: {', '.join(sorted(AUTHORIZED_DIMENSIONS))}"
        )

    return None


def validate_lens(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate lens field uses authorized vocabulary.

    Lens pattern: {category}.{attribute}
    - category: functional | emotional | social
    - attribute: specific lens from convention catalog

    Returns: Error message if invalid, None if valid
    """
    lens = wmbt_data.get("lens")

    if not lens:
        return f"Missing required field 'lens'"

    # Check pattern: category.attribute
    if "." not in lens:
        return (
            f"Lens '{lens}' must follow pattern: {{category}}.{{attribute}} "
            f"(e.g., 'functional.efficiency', 'emotional.trust')"
        )

    parts = lens.split(".", 1)
    category = parts[0]
    attribute = parts[1] if len(parts) > 1 else ""

    # Validate category
    if category not in AUTHORIZED_LENS_CATEGORIES:
        return (
            f"Lens category '{category}' is not authorized. "
            f"Must be one of: {', '.join(sorted(AUTHORIZED_LENS_CATEGORIES))}"
        )

    # Validate attribute based on category
    if category == "functional":
        if attribute not in AUTHORIZED_FUNCTIONAL_LENSES:
            return (
                f"Functional lens attribute '{attribute}' is not authorized. "
                f"Must be one of: {', '.join(sorted(AUTHORIZED_FUNCTIONAL_LENSES))}"
            )
    elif category == "emotional":
        if attribute not in AUTHORIZED_EMOTIONAL_LENSES:
            return (
                f"Emotional lens attribute '{attribute}' is not authorized. "
                f"Must be one of: {', '.join(sorted(AUTHORIZED_EMOTIONAL_LENSES))}"
            )
    elif category == "social":
        if attribute not in AUTHORIZED_SOCIAL_LENSES:
            return (
                f"Social lens attribute '{attribute}' is not authorized. "
                f"Must be one of: {', '.join(sorted(AUTHORIZED_SOCIAL_LENSES))}"
            )

    return None


def validate_object_of_control(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate object_of_control follows naming convention.

    Pattern: kebab-case noun phrase (lowercase, hyphens, no spaces)

    Returns: Error message if invalid, None if valid
    """
    object_of_control = wmbt_data.get("object_of_control")

    if not object_of_control:
        return f"Missing required field 'object_of_control'"

    # Must be kebab-case
    if not re.match(r'^[a-z][a-z0-9-]*$', object_of_control):
        return (
            f"Object of control '{object_of_control}' must be kebab-case "
            f"(lowercase letters, numbers, hyphens only, starting with letter)"
        )

    if len(object_of_control) < 2:
        return f"Object of control '{object_of_control}' is too short (min 2 chars)"

    return None


def validate_statement_construction(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate statement follows construction pattern.

    Pattern: {direction} {dimension} of {object_of_control} {context_clarifier}

    Returns: Error message if invalid, None if valid
    """
    statement = wmbt_data.get("statement")

    if not statement:
        return f"Missing required field 'statement'"

    direction = wmbt_data.get("direction", "")
    dimension = wmbt_data.get("dimension", "")
    object_of_control = wmbt_data.get("object_of_control", "")
    context_clarifier = wmbt_data.get("context_clarifier", "")

    # Build expected statement pattern
    expected_parts = [direction, dimension, "of", object_of_control]
    if context_clarifier:
        expected_parts.append(context_clarifier)

    # Check if statement contains expected components
    statement_lower = statement.lower()

    # Must start with direction
    if not statement_lower.startswith(direction.lower()):
        return (
            f"Statement must start with direction '{direction}'. "
            f"Current: '{statement}'"
        )

    # Must contain dimension
    if dimension.lower() not in statement_lower:
        return (
            f"Statement must contain dimension '{dimension}'. "
            f"Current: '{statement}'"
        )

    # Must contain "of" separator
    if " of " not in statement_lower:
        return (
            f"Statement must contain ' of ' separator. "
            f"Current: '{statement}'"
        )

    # Must contain object_of_control (with hyphens converted to spaces for natural language)
    object_natural = object_of_control.replace("-", " ")
    if object_natural.lower() not in statement_lower and object_of_control.lower() not in statement_lower:
        return (
            f"Statement must contain object of control '{object_of_control}'. "
            f"Current: '{statement}'"
        )

    return None


def validate_urn_step_code_consistency(wmbt_data: Dict, file_path: Path) -> Optional[str]:
    """
    Validate URN step code matches step field.

    URN format: wmbt:{wagon}:{STEP_CODE}{NNN}
    Step code in URN must match the step field.

    Returns: Error message if invalid, None if valid
    """
    urn = wmbt_data.get("urn", "")
    step = wmbt_data.get("step", "")

    if not urn or not step:
        return None  # Other validators will catch missing fields

    # Extract step code from URN
    # Pattern: wmbt:{wagon}:{STEP_CODE}{NNN}
    parts = urn.split(":")
    if len(parts) < 3:
        return None  # URN pattern validation is handled elsewhere

    code_part = parts[2]  # e.g., "E001"
    if not code_part:
        return None

    urn_step_code = code_part[0]  # e.g., "E"

    # Get expected step code from step field
    expected_step_code = AUTHORIZED_STEPS.get(step)

    if not expected_step_code:
        return None  # Step validation is handled elsewhere

    if urn_step_code != expected_step_code:
        return (
            f"URN step code '{urn_step_code}' does not match step field '{step}'. "
            f"Expected step code: '{expected_step_code}' (from step '{step}'). "
            f"URN: {urn}"
        )

    return None


@pytest.mark.planner
def test_wmbt_files_use_authorized_steps():
    """
    SPEC-PLANNER-WMBT-VOCAB-001: WMBT files use authorized step vocabulary.

    Given: WMBT YAML files in plan/{wagon}/ directories
    When: Validating step field
    Then: Step must be one of the authorized values from convention

    Authorized steps: define, locate, prepare, confirm, execute, monitor, modify, resolve, conclude
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: Failed to load file")
            continue

        error = validate_step(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} step vocabulary violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )


@pytest.mark.planner
def test_wmbt_files_use_authorized_directions():
    """
    SPEC-PLANNER-WMBT-VOCAB-002: WMBT files use authorized direction vocabulary.

    Given: WMBT YAML files in plan/{wagon}/ directories
    When: Validating direction field
    Then: Direction must be one of the authorized values from convention

    Authorized directions: minimize, maximize, increase, decrease
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            continue

        error = validate_direction(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} direction vocabulary violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )


@pytest.mark.planner
def test_wmbt_files_use_authorized_dimensions():
    """
    SPEC-PLANNER-WMBT-VOCAB-003: WMBT files use authorized dimension vocabulary.

    Given: WMBT YAML files in plan/{wagon}/ directories
    When: Validating dimension field
    Then: Dimension must be one of the authorized values from convention

    Authorized dimensions: time, effort, likelihood, frequency, quantity, financial value
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            continue

        error = validate_dimension(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} dimension vocabulary violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )


@pytest.mark.planner
def test_wmbt_files_use_authorized_lenses():
    """
    SPEC-PLANNER-WMBT-VOCAB-004: WMBT files use authorized lens vocabulary.

    Given: WMBT YAML files in plan/{wagon}/ directories
    When: Validating lens field
    Then: Lens must follow pattern {category}.{attribute} with authorized values

    Authorized categories: functional, emotional, social
    Authorized attributes defined per category in convention
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            continue

        error = validate_lens(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} lens vocabulary violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )


@pytest.mark.planner
def test_wmbt_files_have_valid_object_of_control():
    """
    SPEC-PLANNER-WMBT-VOCAB-005: WMBT files have valid object_of_control format.

    Given: WMBT YAML files in plan/{wagon}/ directories
    When: Validating object_of_control field
    Then: Must be kebab-case noun phrase (lowercase, hyphens, min 2 chars)
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            continue

        error = validate_object_of_control(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} object_of_control format violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )


@pytest.mark.planner
def test_wmbt_statements_follow_construction_pattern():
    """
    SPEC-PLANNER-WMBT-VOCAB-006: WMBT statements follow construction pattern.

    Given: WMBT YAML files in plan/{wagon}/ directories
    When: Validating statement field
    Then: Statement must follow pattern: {direction} {dimension} of {object_of_control} {context_clarifier}

    Pattern ensures consistency and readability across all WMBT statements.
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            continue

        error = validate_statement_construction(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} statement construction violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )


@pytest.mark.planner
def test_wmbt_urn_step_code_matches_step_field():
    """
    SPEC-PLANNER-WMBT-VOCAB-007: WMBT URN step code matches step field.

    Given: WMBT YAML files with URN and step fields
    When: Validating URN step code against step field
    Then: Step code in URN must match step field

    Example:
    - URN: wmbt:resolve-dilemmas:E001 (step code: E)
    - Step: execute (maps to: E)
    - Result: Valid (E matches E)
    """
    wmbt_files = find_wmbt_files()

    if not wmbt_files:
        pytest.skip("No WMBT files found")

    violations = []

    for wagon_slug, wmbt_file in wmbt_files:
        wmbt_data = load_wmbt_file(wmbt_file)

        if not wmbt_data:
            continue

        error = validate_urn_step_code_consistency(wmbt_data, wmbt_file)
        if error:
            violations.append(f"{wmbt_file.relative_to(REPO_ROOT)}: {error}")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} URN-step consistency violations:\n\n" +
            "\n".join(violations[:20]) +
            (f"\n\n... and {len(violations) - 20} more" if len(violations) > 20 else "")
        )
