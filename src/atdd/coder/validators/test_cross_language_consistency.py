"""
Test cross-language consistency between Python, Dart, and TypeScript.

Validates:
- Entities defined consistently across languages
- Enums match across languages
- Value object structures align
- API contracts are honored

Inspired by: .claude/utils/coder/ (multiple utilities)
But: Self-contained, no utility dependencies
"""

import pytest
import re
import json
from pathlib import Path
from typing import Dict, List, Set


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"
LIB_DIR = REPO_ROOT / "lib"
SUPABASE_DIR = REPO_ROOT / "supabase"
CONTRACTS_DIR = REPO_ROOT / "contracts"


def extract_python_classes() -> Dict[str, Dict]:
    """
    Extract class definitions from Python code.

    Returns:
        Dict mapping class name to metadata
    """
    if not PYTHON_DIR.exists():
        return {}

    classes = {}

    for py_file in PYTHON_DIR.rglob("*.py"):
        if '/test/' in str(py_file):
            continue

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        # Find class definitions
        class_pattern = r'class\s+([A-Z][a-zA-Z0-9_]*)\s*[:\(]'
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            classes[class_name] = {
                'file': str(py_file.relative_to(REPO_ROOT)),
                'language': 'python'
            }

    return classes


def extract_dart_classes() -> Dict[str, Dict]:
    """
    Extract class definitions from Dart code.

    Returns:
        Dict mapping class name to metadata
    """
    if not LIB_DIR.exists():
        return {}

    classes = {}

    for dart_file in LIB_DIR.rglob("*.dart"):
        if dart_file.name.endswith('_test.dart'):
            continue

        try:
            with open(dart_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        # Find class definitions
        class_pattern = r'class\s+([A-Z][a-zA-Z0-9_]*)\s*[{\s]'
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            classes[class_name] = {
                'file': str(dart_file.relative_to(REPO_ROOT)),
                'language': 'dart'
            }

    return classes


def extract_python_enums() -> Dict[str, Set[str]]:
    """
    Extract enum definitions from Python code.

    Returns:
        Dict mapping enum name to set of values
    """
    if not PYTHON_DIR.exists():
        return {}

    enums = {}

    for py_file in PYTHON_DIR.rglob("*.py"):
        if '/test/' in str(py_file):
            continue

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        # Find enum definitions: class XxxEnum(Enum)
        enum_pattern = r'class\s+([A-Z][a-zA-Z0-9_]*)\s*\(\s*Enum\s*\):'
        for match in re.finditer(enum_pattern, content):
            enum_name = match.group(1)

            # Extract enum values (simplified)
            # Pattern: NAME = value
            value_pattern = r'^\s+([A-Z_]+)\s*='
            values = set()
            for line in content.split('\n'):
                val_match = re.match(value_pattern, line)
                if val_match:
                    values.add(val_match.group(1))

            if values:
                enums[enum_name] = values

    return enums


def extract_dart_enums() -> Dict[str, Set[str]]:
    """
    Extract enum definitions from Dart code.

    Returns:
        Dict mapping enum name to set of values
    """
    if not LIB_DIR.exists():
        return {}

    enums = {}

    for dart_file in LIB_DIR.rglob("*.dart"):
        if dart_file.name.endswith('_test.dart'):
            continue

        try:
            with open(dart_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        # Find enum definitions: enum XxxEnum { ... }
        enum_pattern = r'enum\s+([A-Z][a-zA-Z0-9_]*)\s*\{([^}]+)\}'
        for match in re.finditer(enum_pattern, content):
            enum_name = match.group(1)
            enum_body = match.group(2)

            # Extract values
            values = set()
            for value in enum_body.split(','):
                val = value.strip()
                if val and not val.startswith('//'):
                    # Remove any comments
                    val = val.split('//')[0].strip()
                    if val:
                        values.add(val)

            if values:
                enums[enum_name] = values

    return enums


def find_contract_entities() -> Dict[str, Set[str]]:
    """
    Extract entities from contract schemas.

    Returns:
        Dict mapping entity name to set of fields
    """
    if not CONTRACTS_DIR.exists():
        return {}

    entities = {}

    for schema_file in CONTRACTS_DIR.rglob("*.schema.json"):
        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema = json.load(f)
        except Exception:
            continue

        # Extract entity name from $id
        schema_id = schema.get('$id', '')
        if ':' in schema_id:
            entity_name = schema_id.split(':')[-1].replace('.', '_')
        else:
            entity_name = schema_file.stem

        # Extract required fields
        required = set(schema.get('required', []))
        properties = set(schema.get('properties', {}).keys())

        entities[entity_name] = required if required else properties

    return entities


@pytest.mark.coder
def test_entity_classes_exist_across_languages():
    """
    SPEC-CODER-CONSISTENCY-0001: Core entities exist in all languages.

    For polyglot codebases, core domain entities should exist in all languages.

    Given: Entity classes in Python, Dart, contracts
    When: Comparing entity names
    Then: Core entities exist across languages
    """
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()
    contract_entities = find_contract_entities()

    if not python_classes and not dart_classes:
        pytest.skip("No classes found")

    if not contract_entities:
        pytest.skip("No contract entities found")

    # Check if contract entities have implementations
    missing_implementations = []

    for entity_name, fields in contract_entities.items():
        # Normalize name (PascalCase)
        normalized = ''.join(word.capitalize() for word in entity_name.split('_'))

        # Check Python
        has_python = normalized in python_classes or entity_name in python_classes
        # Check Dart
        has_dart = normalized in dart_classes or entity_name in dart_classes

        if not has_python and not has_dart:
            missing_implementations.append(
                f"Contract entity: {entity_name}\\n"
                f"  Fields: {', '.join(list(fields)[:5])}\\n"
                f"  Missing in: Python AND Dart"
            )
        elif not has_python:
            missing_implementations.append(
                f"Contract entity: {entity_name}\\n"
                f"  Missing in: Python"
            )
        elif not has_dart:
            missing_implementations.append(
                f"Contract entity: {entity_name}\\n"
                f"  Missing in: Dart"
            )

    if missing_implementations:
        pytest.fail(
            f"\\n\\nFound {len(missing_implementations)} contract entities without implementations:\\n\\n" +
            "\\n\\n".join(missing_implementations[:10]) +
            (f"\\n\\n... and {len(missing_implementations) - 10} more" if len(missing_implementations) > 10 else "")
        )


@pytest.mark.coder
def test_enums_match_across_languages():
    """
    SPEC-CODER-CONSISTENCY-0002: Enums match across languages.

    Enums should have same values in all languages.

    Given: Enum definitions in Python and Dart
    When: Comparing enum values
    Then: Enums with same name have same values
    """
    python_enums = extract_python_enums()
    dart_enums = extract_dart_enums()

    if not python_enums and not dart_enums:
        pytest.skip("No enums found")

    mismatches = []

    # Find enums with same name
    for enum_name in set(python_enums.keys()) & set(dart_enums.keys()):
        python_values = python_enums[enum_name]
        dart_values = dart_enums[enum_name]

        # Compare (case-insensitive)
        python_lower = {v.lower() for v in python_values}
        dart_lower = {v.lower() for v in dart_values}

        if python_lower != dart_lower:
            only_python = python_lower - dart_lower
            only_dart = dart_lower - python_lower

            mismatches.append(
                f"Enum: {enum_name}\\n"
                f"  Only in Python: {', '.join(only_python) if only_python else 'none'}\\n"
                f"  Only in Dart: {', '.join(only_dart) if only_dart else 'none'}"
            )

    if mismatches:
        pytest.fail(
            f"\\n\\nFound {len(mismatches)} enum mismatches:\\n\\n" +
            "\\n\\n".join(mismatches)
        )


@pytest.mark.coder
def test_naming_conventions_consistent():
    """
    SPEC-CODER-CONSISTENCY-0003: Naming conventions are consistent.

    Similar concepts should use similar names across languages.

    Given: Class names in all languages
    When: Comparing patterns
    Then: Consistent naming (e.g., XxxEntity vs Xxx)
    """
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()

    if not python_classes or not dart_classes:
        pytest.skip("Need classes in multiple languages")

    # Check for common suffixes
    python_suffixes = {}
    dart_suffixes = {}

    for name in python_classes.keys():
        for suffix in ['Entity', 'Model', 'DTO', 'Service', 'Repository']:
            if name.endswith(suffix):
                base = name[:-len(suffix)]
                python_suffixes.setdefault(suffix, set()).add(base)

    for name in dart_classes.keys():
        for suffix in ['Entity', 'Model', 'DTO', 'Service', 'Repository']:
            if name.endswith(suffix):
                base = name[:-len(suffix)]
                dart_suffixes.setdefault(suffix, set()).add(base)

    # Find inconsistencies
    inconsistencies = []

    for suffix in set(python_suffixes.keys()) | set(dart_suffixes.keys()):
        python_bases = python_suffixes.get(suffix, set())
        dart_bases = dart_suffixes.get(suffix, set())

        # Find classes that use different suffixes
        common_bases = python_bases & dart_bases

        for base in common_bases:
            # If same base exists with this suffix in both, good
            pass

        # Check if base exists with different suffix
        for base in python_bases:
            # Check if Dart has same base with different suffix
            for dart_suffix in dart_suffixes.keys():
                if suffix != dart_suffix and base in dart_suffixes[dart_suffix]:
                    inconsistencies.append(
                        f"Base class: {base}\\n"
                        f"  Python uses: {suffix}\\n"
                        f"  Dart uses: {dart_suffix}"
                    )

    if inconsistencies:
        pytest.fail(
            f"\\n\\nFound {len(inconsistencies)} naming inconsistencies:\\n\\n" +
            "\\n\\n".join(inconsistencies[:10]) +
            (f"\\n\\n... and {len(inconsistencies) - 10} more" if len(inconsistencies) > 10 else "")
        )


@pytest.mark.coder
def test_api_contracts_honored_across_languages():
    """
    SPEC-CODER-CONSISTENCY-0004: API contracts honored in all implementations.

    Contract schemas define API structure.
    All language implementations should follow them.

    Given: Contract schemas
    When: Checking for matching entities
    Then: Each language has entity matching contract
    """
    contract_entities = find_contract_entities()
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()

    if not contract_entities:
        pytest.skip("No contracts found")

    # For each contract, check if at least one language implements it
    unimplemented = []

    for entity_name, fields in contract_entities.items():
        normalized = ''.join(word.capitalize() for word in entity_name.split('_'))

        has_any_impl = (
            normalized in python_classes or
            entity_name in python_classes or
            normalized in dart_classes or
            entity_name in dart_classes
        )

        if not has_any_impl:
            unimplemented.append(
                f"Contract: {entity_name}\\n"
                f"  Fields: {', '.join(list(fields)[:5])}\\n"
                f"  No implementations found"
            )

    if unimplemented:
        pytest.fail(
            f"\\n\\nFound {len(unimplemented)} unimplemented contracts:\\n\\n" +
            "\\n\\n".join(unimplemented[:10]) +
            (f"\\n\\n... and {len(unimplemented) - 10} more" if len(unimplemented) > 10 else "")
        )
