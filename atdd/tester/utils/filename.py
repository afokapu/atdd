"""
Test filename generation from acceptance URNs.

Provides utilities to generate test filenames following language-specific
conventions from acceptance URN format.

URN Format: acc:{wagon}:{WMBT}-{HARNESS}-{NNN}[-{slug}]
Example: acc:maintain-ux:C004-E2E-019-user-connection

Spec: SPEC-TESTER-CONV-0068 through SPEC-TESTER-CONV-0076
URN: utils:tester:filename
"""

import re
from typing import Dict, Optional


# URN pattern for acceptance criteria
# Format: acc:{wagon}:{WMBT}-{HARNESS}-{NNN}[-{slug}]
# - wagon: lowercase with hyphens (a-z0-9-)
# - WMBT: Step code + 3-digit sequence (e.g., C004, E019)
# - HARNESS: Uppercase code (UNIT, HTTP, E2E, etc.)
# - NNN: 3-digit zero-padded sequence (001-999)
# - slug: Optional kebab-case descriptor
URN_PATTERN = r'^acc:([a-z][a-z0-9-]*):([DLPCEMYRK][0-9]{3})-([A-Z0-9]+)-([0-9]{3})(?:-([a-z0-9-]+))?$'


def parse_acceptance_urn(urn: str) -> Dict[str, Optional[str]]:
    """
    Parse acceptance URN into components.

    Args:
        urn: Acceptance URN in format acc:{wagon}:{WMBT}-{HARNESS}-{NNN}[-{slug}]

    Returns:
        Dictionary with keys: wagon, WMBT, HARNESS, NNN, slug

    Raises:
        ValueError: If URN format is invalid

    Example:
        >>> parse_acceptance_urn("acc:maintain-ux:C004-E2E-019-user-connection")
        {
            'wagon': 'maintain-ux',
            'WMBT': 'C004',
            'HARNESS': 'E2E',
            'NNN': '019',
            'slug': 'user-connection'
        }
    """
    match = re.match(URN_PATTERN, urn)
    if not match:
        raise ValueError(f"Invalid acceptance URN: {urn}")

    wagon, WMBT, HARNESS, NNN, slug = match.groups()

    return {
        'wagon': wagon,
        'WMBT': WMBT,
        'HARNESS': HARNESS,
        'NNN': NNN,
        'slug': slug  # None if not present
    }


def kebab_to_snake(slug: Optional[str]) -> str:
    """
    Convert kebab-case to snake_case.

    Args:
        slug: Kebab-case string (e.g., "user-connection")

    Returns:
        Snake_case string (e.g., "user_connection")

    Example:
        >>> kebab_to_snake("user-connection")
        'user_connection'
    """
    if not slug:
        return ""
    return slug.replace('-', '_')


def kebab_to_pascal(slug: Optional[str]) -> str:
    """
    Convert kebab-case to PascalCase.

    Args:
        slug: Kebab-case string (e.g., "user-connection")

    Returns:
        PascalCase string (e.g., "UserConnection")

    Example:
        >>> kebab_to_pascal("user-connection")
        'UserConnection'
    """
    if not slug:
        return ""
    return ''.join(part.capitalize() for part in slug.split('-'))


def dart_filename(urn: str) -> str:
    """
    Generate Dart test filename from acceptance URN.

    Pattern: {WMBT}_{HARNESS}_{NNN}[_{slug_snake}]_test.dart
    - WMBT and HARNESS remain uppercase
    - Underscore separators
    - Slug converted to snake_case

    Args:
        urn: Acceptance URN

    Returns:
        Dart test filename

    Example:
        >>> dart_filename("acc:maintain-ux:C004-E2E-019-user-connection")
        'C004_E2E_019_user_connection_test.dart'
    """
    parts = parse_acceptance_urn(urn)
    slug_part = f"_{kebab_to_snake(parts['slug'])}" if parts['slug'] else ""
    return f"{parts['WMBT']}_{parts['HARNESS']}_{parts['NNN']}{slug_part}_test.dart"


def typescript_filename(urn: str) -> str:
    """
    Generate TypeScript test filename from acceptance URN.

    Pattern: {wmbt_lower}-{harness_lower}-{nnn}[-{slug-kebab}].test.ts
    - All components lowercase
    - Hyphen separators
    - Slug preserved in kebab-case

    Args:
        urn: Acceptance URN

    Returns:
        TypeScript test filename

    Example:
        >>> typescript_filename("acc:maintain-ux:C004-E2E-019-user-connection")
        'c004-e2e-019-user-connection.test.ts'
    """
    parts = parse_acceptance_urn(urn)
    slug_part = f"-{parts['slug']}" if parts['slug'] else ""
    return f"{parts['WMBT'].lower()}-{parts['HARNESS'].lower()}-{parts['NNN']}{slug_part}.test.ts"


def typescript_preact_filename(urn: str, tsx: Optional[bool] = None) -> str:
    """
    Generate Preact TypeScript test filename from acceptance URN.

    Pattern: {WMBT}_{HARNESS}_{NNN}[_{slug_snake}].test.ts[x]
    - WMBT and HARNESS remain uppercase
    - Underscore separators
    - Slug converted to snake_case
    - .test.tsx reserved for widget/component tests

    Args:
        urn: Acceptance URN
        tsx: Force .test.tsx if True, .test.ts if False. Defaults to None
             which uses HARNESS == WIDGET to decide.

    Returns:
        Preact TypeScript test filename
    """
    parts = parse_acceptance_urn(urn)
    slug_part = f"_{kebab_to_snake(parts['slug'])}" if parts['slug'] else ""
    use_tsx = tsx if tsx is not None else parts['HARNESS'] == "WIDGET"
    suffix = ".test.tsx" if use_tsx else ".test.ts"
    return f"{parts['WMBT']}_{parts['HARNESS']}_{parts['NNN']}{slug_part}{suffix}"


def python_filename(urn: str) -> str:
    """
    Generate Python test filename from acceptance URN.

    Pattern: test_{wmbt_lower}_{harness_lower}_{nnn}[_{slug_snake}].py
    - Prefix "test_" required by pytest
    - All components lowercase
    - Underscore separators
    - Slug converted to snake_case

    Args:
        urn: Acceptance URN

    Returns:
        Python test filename

    Example:
        >>> python_filename("acc:maintain-ux:C004-E2E-019-user-connection")
        'test_c004_e2e_019_user_connection.py'
    """
    parts = parse_acceptance_urn(urn)
    slug_part = f"_{kebab_to_snake(parts['slug'])}" if parts['slug'] else ""
    return f"test_{parts['WMBT'].lower()}_{parts['HARNESS'].lower()}_{parts['NNN']}{slug_part}.py"


def go_filename(urn: str) -> str:
    """
    Generate Go test filename from acceptance URN.

    Pattern: {wmbt_lower}_{harness_lower}_{nnn}[_{slug_snake}]_test.go
    - All components lowercase
    - Underscore separators
    - Slug converted to snake_case

    Args:
        urn: Acceptance URN

    Returns:
        Go test filename

    Example:
        >>> go_filename("acc:maintain-ux:C004-E2E-019-user-connection")
        'c004_e2e_019_user_connection_test.go'
    """
    parts = parse_acceptance_urn(urn)
    slug_part = f"_{kebab_to_snake(parts['slug'])}" if parts['slug'] else ""
    return f"{parts['WMBT'].lower()}_{parts['HARNESS'].lower()}_{parts['NNN']}{slug_part}_test.go"


def java_classname(urn: str) -> str:
    """
    Generate Java/Kotlin test classname from acceptance URN.

    Pattern: {WMBT}{HARNESS}{NNN}{SlugPascal}Test
    - WMBT and HARNESS uppercase
    - Slug converted to PascalCase
    - No separators
    - Suffix "Test"

    Args:
        urn: Acceptance URN

    Returns:
        Java/Kotlin test classname

    Example:
        >>> java_classname("acc:maintain-ux:C004-E2E-019-user-connection")
        'C004E2E019UserConnectionTest'
    """
    parts = parse_acceptance_urn(urn)
    slug_part = kebab_to_pascal(parts['slug']) if parts['slug'] else ""
    return f"{parts['WMBT']}{parts['HARNESS']}{parts['NNN']}{slug_part}Test"


def generate_test_filename(urn: str, language: str) -> str:
    """
    Generate test filename for specified language from acceptance URN.

    Unified interface that routes to language-specific generators.

    Args:
        urn: Acceptance URN
        language: Target language (dart, typescript, typescript_preact, python, go, java, kotlin)

    Returns:
        Test filename for specified language

    Raises:
        ValueError: If language is not supported

    Example:
        >>> generate_test_filename("acc:maintain-ux:C004-E2E-019", "python")
        'test_c004_e2e_019.py'
    """
    generators = {
        'dart': dart_filename,
        'typescript': typescript_filename,
        'typescript_preact': typescript_preact_filename,
        'python': python_filename,
        'go': go_filename,
        'java': lambda urn: java_classname(urn) + ".java",
        'kotlin': lambda urn: java_classname(urn) + ".kt",
    }

    if language not in generators:
        raise ValueError(f"Unsupported language: {language}")

    return generators[language](urn)


# Export all public functions
__all__ = [
    'URN_PATTERN',
    'parse_acceptance_urn',
    'kebab_to_snake',
    'kebab_to_pascal',
    'dart_filename',
    'typescript_filename',
    'typescript_preact_filename',
    'python_filename',
    'go_filename',
    'java_classname',
    'generate_test_filename',
]
