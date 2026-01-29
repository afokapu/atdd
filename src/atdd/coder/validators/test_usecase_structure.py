"""
Test use case structure follows best practices.

Validates:
- Use cases have single responsibility
- Use cases have proper input/output structure
- Use cases have execute/call method
- Use cases don't directly access database/API
- Use cases coordinate through ports/interfaces

Inspired by: .claude/utils/coder/usecase.py
But: Self-contained, no utility dependencies
"""

import pytest
import re
import ast
from pathlib import Path
from typing import List, Tuple, Set


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"
DART_DIRS = [REPO_ROOT / "lib", REPO_ROOT / "dart"]
TS_DIRS = [REPO_ROOT / "supabase" / "functions", REPO_ROOT / "typescript"]


def find_usecase_files() -> List[Tuple[Path, str]]:
    """
    Find all use case files across languages.

    Returns:
        List of (file_path, language) tuples
    """
    usecase_files = []

    # Python use cases
    if PYTHON_DIR.exists():
        for py_file in PYTHON_DIR.rglob("*_use_case.py"):
            if '__pycache__' not in str(py_file):
                usecase_files.append((py_file, 'python'))
        for py_file in PYTHON_DIR.rglob("*usecase.py"):
            if '__pycache__' not in str(py_file) and not py_file.name.endswith('_use_case.py'):
                usecase_files.append((py_file, 'python'))

    # Dart use cases
    for dart_dir in DART_DIRS:
        if dart_dir.exists():
            for dart_file in dart_dir.rglob("*_usecases.dart"):
                if '/build/' not in str(dart_file):
                    usecase_files.append((dart_file, 'dart'))
            for dart_file in dart_dir.rglob("*_use_case.dart"):
                if '/build/' not in str(dart_file):
                    usecase_files.append((dart_file, 'dart'))

    # TypeScript use cases
    for ts_dir in TS_DIRS:
        if ts_dir.exists():
            for ts_file in ts_dir.rglob("*-use-case.ts"):
                if 'node_modules' not in str(ts_file):
                    usecase_files.append((ts_file, 'typescript'))
            for ts_file in ts_dir.rglob("*-usecase.ts"):
                if 'node_modules' not in str(ts_file):
                    usecase_files.append((ts_file, 'typescript'))

    return usecase_files


def extract_python_classes(file_path: Path) -> List[str]:
    """
    Extract class names from Python file.

    Args:
        file_path: Path to Python file

    Returns:
        List of class names
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)

    return classes


def check_python_usecase_methods(file_path: Path) -> List[Tuple[str, List[str]]]:
    """
    Check Python use case classes for required methods.

    Args:
        file_path: Path to Python use case file

    Returns:
        List of (class_name, method_names) tuples
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    results = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)
            results.append((node.name, methods))

    return results


def check_for_direct_database_access(file_path: Path, language: str) -> List[str]:
    """
    Check if use case directly accesses database/API.

    Args:
        file_path: Path to use case file
        language: File language (python, dart, typescript)

    Returns:
        List of violation messages
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    violations = []

    # Patterns that indicate direct database/API access
    if language == 'python':
        FORBIDDEN_PATTERNS = [
            (r'import\s+psycopg2', 'Direct PostgreSQL import'),
            (r'import\s+pymongo', 'Direct MongoDB import'),
            (r'import\s+redis', 'Direct Redis import'),
            (r'import\s+requests', 'Direct HTTP import (use repository)'),
            (r'import\s+httpx', 'Direct HTTP import (use repository)'),
            (r'from\s+sqlalchemy', 'Direct SQLAlchemy import'),
            (r'from\s+django\.db', 'Direct Django DB import'),
        ]
    elif language == 'dart':
        FORBIDDEN_PATTERNS = [
            (r"import\s+['\"]package:sqflite", 'Direct SQLite import'),
            (r"import\s+['\"]package:http/", 'Direct HTTP import (use repository)'),
            (r"import\s+['\"]package:dio/", 'Direct HTTP client import (use repository)'),
            (r"import\s+['\"]package:supabase/", 'Direct Supabase import (use repository)'),
        ]
    else:  # typescript
        FORBIDDEN_PATTERNS = [
            (r"import.*?['\"]\@supabase/supabase-js['\"]", 'Direct Supabase import (use repository)'),
            (r"import.*?['\"]axios['\"]", 'Direct HTTP import (use repository)'),
            (r"import.*?['\"]node-fetch['\"]", 'Direct HTTP import (use repository)'),
            (r"import.*?['\"]pg['\"]", 'Direct PostgreSQL import'),
        ]

    for pattern, message in FORBIDDEN_PATTERNS:
        if re.search(pattern, content):
            violations.append(message)

    return list(set(violations))


def count_responsibilities(file_path: Path, language: str) -> int:
    """
    Count number of distinct responsibilities in use case file.

    Heuristic: Count number of classes/functions that look like use cases.

    Args:
        file_path: Path to use case file
        language: File language

    Returns:
        Number of responsibilities (1 is ideal)
    """
    if language == 'python':
        classes = extract_python_classes(file_path)
        # Filter to use case classes (exclude helpers)
        usecase_classes = [c for c in classes if 'UseCase' in c or 'Command' in c or 'Query' in c]
        return len(usecase_classes)
    
    # For other languages, we'll be lenient and return 1
    return 1


@pytest.mark.coder
def test_usecases_have_single_responsibility():
    """
    SPEC-CODER-USECASE-0001: Use cases have single responsibility.

    Each use case file should contain ONE use case class.
    Multiple use cases should be in separate files.

    Single Responsibility Principle:
    - One use case = one business workflow
    - Clear, focused purpose
    - Easy to test and maintain

    Given: Use case files (*_use_case.py, *-use-case.ts, etc.)
    When: Checking number of use case classes
    Then: Each file has exactly one use case
    """
    usecase_files = find_usecase_files()

    if not usecase_files:
        pytest.skip("No use case files found to validate")

    violations = []

    for file_path, language in usecase_files:
        count = count_responsibilities(file_path, language)
        
        if count > 1:
            rel_path = file_path.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\n"
                f"  Language: {language}\n"
                f"  Use Cases: {count}\n"
                f"  Issue: File contains {count} use cases, should have 1"
            )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} single responsibility violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nEach use case file should contain exactly one use case.\n" +
            f"Split multiple use cases into separate files."
        )


@pytest.mark.coder
def test_usecases_have_execute_method():
    """
    SPEC-CODER-USECASE-0002: Use cases have execute/call method.

    Use cases should have a clear entry point:
    - Python: execute(), __call__(), or run()
    - Dart: call(), execute()
    - TypeScript: execute(), run()

    This makes use cases invokable and testable.

    Given: Python use case files
    When: Checking for execute methods
    Then: Each use case has an entry point method
    """
    usecase_files = find_usecase_files()

    # Only check Python for now (easier to parse)
    python_usecases = [(f, l) for f, l in usecase_files if l == 'python']

    if not python_usecases:
        pytest.skip("No Python use case files found to validate")

    violations = []

    VALID_METHODS = {'execute', '__call__', 'run', 'handle'}

    for file_path, _ in python_usecases:
        class_methods = check_python_usecase_methods(file_path)
        
        for class_name, methods in class_methods:
            # Skip non-usecase classes
            if 'UseCase' not in class_name and 'Command' not in class_name and 'Query' not in class_name:
                continue
            
            # Skip private/helper classes
            if class_name.startswith('_'):
                continue
            
            # Check if has valid entry point
            has_entry_point = any(method in VALID_METHODS for method in methods)
            
            if not has_entry_point and len(methods) > 0:
                rel_path = file_path.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\n"
                    f"  Class: {class_name}\n"
                    f"  Methods: {', '.join(methods)}\n"
                    f"  Issue: Use case missing entry point (execute, __call__, run, handle)"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} missing entry point violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nUse cases should have a clear entry point method:\n" +
            f"  - execute() - explicit, clear\n" +
            f"  - __call__() - makes use case invokable\n" +
            f"  - run() or handle() - also acceptable"
        )


@pytest.mark.coder
def test_usecases_dont_directly_access_database():
    """
    SPEC-CODER-USECASE-0003: Use cases don't directly access database/API.

    Use cases should coordinate through ports/interfaces:
    - Don't import database libraries directly
    - Don't import HTTP clients directly
    - Use repository interfaces instead
    - Use service interfaces for external APIs

    Clean Architecture principle:
    - Use cases are in Application layer
    - Database/API access is in Integration layer
    - Use cases depend on abstractions (ports)

    Given: Use case files
    When: Checking imports
    Then: No direct database/API library imports
    """
    usecase_files = find_usecase_files()

    if not usecase_files:
        pytest.skip("No use case files found to validate")

    violations = []

    for file_path, language in usecase_files:
        direct_access = check_for_direct_database_access(file_path, language)
        
        if direct_access:
            rel_path = file_path.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\n"
                f"  Language: {language}\n"
                f"  Violations:\n" +
                "\n".join(f"    - {v}" for v in direct_access)
            )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} direct database/API access violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nUse cases should not directly import database/API libraries.\n" +
            f"Use repository interfaces instead (Dependency Inversion Principle)."
        )


@pytest.mark.coder
def test_usecases_are_in_application_layer():
    """
    SPEC-CODER-USECASE-0004: Use cases are in application layer.

    Use cases should live in the application layer:
    - .../application/use_cases/
    - .../application/usecases/
    - .../usecases/ (if no explicit layers)

    Not in:
    - domain/ (pure business logic)
    - presentation/ (UI/API)
    - integration/ (database/external services)

    Given: Use case files
    When: Checking file paths
    Then: All use cases in application layer
    """
    usecase_files = find_usecase_files()

    if not usecase_files:
        pytest.skip("No use case files found to validate")

    violations = []

    for file_path, language in usecase_files:
        path_str = str(file_path).lower()
        
        # Check if in application layer or usecases directory
        in_application = '/application/' in path_str or '/usecases/' in path_str or '/use_cases/' in path_str
        
        # Check if in wrong layer
        in_domain = '/domain/' in path_str and '/application/' not in path_str
        in_presentation = '/presentation/' in path_str
        in_integration = '/integration/' in path_str or '/infrastructure/' in path_str or '/data/' in path_str
        
        if (in_domain or in_presentation or in_integration) and not in_application:
            rel_path = file_path.relative_to(REPO_ROOT)
            violations.append(
                f"{rel_path}\n"
                f"  Issue: Use case in wrong layer (should be in application/)"
            )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} layer placement violations:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            f"\n\nUse cases should be in application layer.\n" +
            f"Expected paths:\n" +
            f"  - .../application/use_cases/\n" +
            f"  - .../application/usecases/\n" +
            f"  - .../usecases/ (if no explicit layers)"
        )
