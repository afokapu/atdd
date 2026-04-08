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

from atdd.coach.utils.repo import find_repo_root, find_python_dir


# Path constants
REPO_ROOT = find_repo_root()
PYTHON_DIR = find_python_dir(REPO_ROOT)
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

        # Skip cross-cutting shape contracts (e.g., error response)
        # that define wire formats rather than domain entities.
        # These use wildcard paths (/*) since they apply to all endpoints.
        metadata = schema.get('x-artifact-metadata', {})
        operations = metadata.get('api', {}).get('operations', [])
        if any(op.get('path', '').startswith('/*') for op in operations):
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


def scan_entity_cross_language(repo_root: Path):
    """Scan for missing entity implementations. Used by ratchet baseline."""
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()
    contract_entities = find_contract_entities()
    if (not python_classes and not dart_classes) or not contract_entities:
        return 0, []
    violations = []
    for entity_name, fields in contract_entities.items():
        normalized = ''.join(word.capitalize() for word in re.split(r'[-_]', entity_name))
        has_python = (normalized in python_classes or entity_name in python_classes or
                      any(normalized in cls for cls in python_classes))
        has_dart = (normalized in dart_classes or entity_name in dart_classes or
                    any(normalized in cls for cls in dart_classes))
        missing = []
        if python_classes and not has_python:
            missing.append("Python")
        if dart_classes and not has_dart:
            missing.append("Dart")
        if missing:
            violations.append(f"{entity_name} missing in {', '.join(missing)}")
    return len(violations), violations


def scan_enum_cross_language(repo_root: Path):
    """Scan for enum mismatches across languages. Used by ratchet baseline."""
    python_enums = extract_python_enums()
    dart_enums = extract_dart_enums()
    if not python_enums and not dart_enums:
        return 0, []
    violations = []
    for enum_name in set(python_enums.keys()) & set(dart_enums.keys()):
        py_lower = {v.lower() for v in python_enums[enum_name]}
        dart_lower = {v.lower() for v in dart_enums[enum_name]}
        if py_lower != dart_lower:
            violations.append(f"{enum_name}: Python={py_lower - dart_lower} Dart={dart_lower - py_lower}")
    return len(violations), violations


def scan_naming_cross_language(repo_root: Path):
    """Scan for naming inconsistencies across languages. Used by ratchet baseline."""
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()
    if not python_classes or not dart_classes:
        return 0, []
    python_suffixes = {}
    dart_suffixes = {}
    for name in python_classes:
        for suffix in ['Entity', 'Model', 'DTO', 'Service', 'Repository']:
            if name.endswith(suffix):
                python_suffixes.setdefault(suffix, set()).add(name[:-len(suffix)])
    for name in dart_classes:
        for suffix in ['Entity', 'Model', 'DTO', 'Service', 'Repository']:
            if name.endswith(suffix):
                dart_suffixes.setdefault(suffix, set()).add(name[:-len(suffix)])
    violations = []
    for suffix in set(python_suffixes.keys()) | set(dart_suffixes.keys()):
        python_bases = python_suffixes.get(suffix, set())
        for base in python_bases:
            for dart_suffix in dart_suffixes:
                if suffix != dart_suffix and base in dart_suffixes[dart_suffix]:
                    violations.append(f"{base}: Python={suffix} Dart={dart_suffix}")
    return len(violations), violations


def scan_api_contracts_cross_language(repo_root: Path):
    """Scan for unimplemented contracts. Used by ratchet baseline."""
    contract_entities = find_contract_entities()
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()
    if not contract_entities:
        return 0, []
    violations = []
    for entity_name, fields in contract_entities.items():
        normalized = ''.join(word.capitalize() for word in re.split(r'[-_]', entity_name))
        has_any = (normalized in python_classes or entity_name in python_classes or
                   normalized in dart_classes or entity_name in dart_classes or
                   any(normalized in cls for cls in python_classes) or
                   any(normalized in cls for cls in dart_classes))
        if not has_any:
            violations.append(f"{entity_name}: no implementations found")
    return len(violations), violations


@pytest.mark.coder
def test_entity_classes_exist_across_languages(ratchet_baseline):
    """
    SPEC-CODER-CONSISTENCY-0001: Core entities exist in all languages.

    Given: Entity classes in Python, Dart, contracts
    When: Comparing entity names
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()
    contract_entities = find_contract_entities()

    if not python_classes and not dart_classes:
        pytest.skip("No classes found")
    if not contract_entities:
        pytest.skip("No contract entities found")

    count, violations = scan_entity_cross_language(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="entity_cross_language",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_enums_match_across_languages(ratchet_baseline):
    """
    SPEC-CODER-CONSISTENCY-0002: Enums match across languages.

    Given: Enum definitions in Python and Dart
    When: Comparing enum values
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_enums = extract_python_enums()
    dart_enums = extract_dart_enums()

    if not python_enums and not dart_enums:
        pytest.skip("No enums found")

    count, violations = scan_enum_cross_language(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="enum_cross_language",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_naming_conventions_consistent(ratchet_baseline):
    """
    SPEC-CODER-CONSISTENCY-0003: Naming conventions are consistent.

    Given: Class names in all languages
    When: Comparing patterns
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    python_classes = extract_python_classes()
    dart_classes = extract_dart_classes()

    if not python_classes or not dart_classes:
        pytest.skip("Need classes in multiple languages")

    count, violations = scan_naming_cross_language(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="naming_cross_language",
        current_count=count,
        violations=violations,
    )


@pytest.mark.coder
def test_api_contracts_honored_across_languages(ratchet_baseline):
    """
    SPEC-CODER-CONSISTENCY-0004: API contracts honored in all implementations.

    Given: Contract schemas
    When: Checking for matching entities
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    contract_entities = find_contract_entities()

    if not contract_entities:
        pytest.skip("No contracts found")

    count, violations = scan_api_contracts_cross_language(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="api_contracts_cross_language",
        current_count=count,
        violations=violations,
    )
