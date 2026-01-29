"""
Test Preact/web frontend follows 4-layer clean architecture boundaries.

Validates Preact-specific architectural rules:
- Domain layer is framework-agnostic (no Preact/React imports)
- Application layer has no JSX (no .tsx files)
- Presentation layer doesn't bypass application layer
- Component tests use correct file extensions

Location: web/src/
Convention: atdd/coder/conventions/frontend.convention.yaml (preact section)

This complements test_typescript_architecture.py which handles Supabase backend TypeScript.
"""

import pytest
import re
from pathlib import Path
from typing import List


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]  # Go up 3 levels: file -> audits -> coder -> atdd -> repo
WEB_SRC = REPO_ROOT / "web" / "src"
WEB_TESTS = REPO_ROOT / "web" / "tests"


def get_typescript_files() -> List[Path]:
    """Find all TypeScript files in web/src/"""
    if not WEB_SRC.exists():
        return []
    return list(WEB_SRC.rglob("*.ts")) + list(WEB_SRC.rglob("*.tsx"))


def get_layer(file_path: Path) -> str:
    """Determine layer from file path"""
    parts = file_path.parts
    if "presentation" in parts:
        return "presentation"
    elif "application" in parts:
        return "application"
    elif "domain" in parts:
        return "domain"
    elif "integration" in parts:
        return "integration"
    return "unknown"


# Pre-filtered layer getters (SESSION-44: reduce skips by filtering at collection time)
def get_domain_files() -> List[Path]:
    """Get only domain layer TypeScript files from web/src"""
    return [f for f in get_typescript_files() if get_layer(f) == "domain"]


def get_presentation_files() -> List[Path]:
    """Get only presentation layer TypeScript files from web/src"""
    return [f for f in get_typescript_files() if get_layer(f) == "presentation"]


def get_application_files() -> List[Path]:
    """Get only application layer TypeScript files from web/src"""
    return [f for f in get_typescript_files() if get_layer(f) == "application"]


def get_test_files() -> List[Path]:
    """Find all test files in web/tests/"""
    if not WEB_TESTS.exists():
        return []
    return list(WEB_TESTS.rglob("*.test.ts")) + list(WEB_TESTS.rglob("*.test.tsx"))


def extract_imports(file_path: Path) -> List[str]:
    """Extract import statements from TypeScript file"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []

    import_pattern = r"import\s+.+\s+from\s+['\"](.+)['\"]"
    return re.findall(import_pattern, content)


@pytest.mark.parametrize("ts_file", get_domain_files())
def test_domain_layer_has_no_framework_imports(ts_file):
    """
    SPEC-CODER-ARCH-PREACT-001: Domain layer must not import UI frameworks

    GIVEN: TypeScript file in domain layer (web/src/.../domain/)
    WHEN: Analyzing imports
    THEN: No imports from 'preact', 'react', or design system aliases

    Rationale: Domain layer must be framework-agnostic for testability and portability
    """
    imports = extract_imports(ts_file)

    forbidden = ['preact', 'react', '@maintain-ux']
    violations = [imp for imp in imports if any(f in imp for f in forbidden)]

    assert not violations, (
        f"Domain layer file {ts_file.relative_to(REPO_ROOT)} has forbidden imports: {violations}\n"
        f"Domain must be framework-agnostic (no UI imports)"
    )


@pytest.mark.parametrize("ts_file", get_presentation_files())
def test_presentation_cannot_import_integration(ts_file):
    """
    SPEC-CODER-ARCH-PREACT-002: Presentation must not bypass application layer

    GIVEN: TypeScript file in presentation layer (web/src/.../presentation/)
    WHEN: Analyzing imports
    THEN: No direct imports from integration layer

    Rationale: Presentation must use application layer (hooks/use cases), not call APIs directly
    """
    imports = extract_imports(ts_file)

    violations = [imp for imp in imports if '/integration/' in imp or '../integration' in imp]

    assert not violations, (
        f"Presentation file {ts_file.relative_to(REPO_ROOT)} imports integration layer: {violations}\n"
        f"Presentation must use application layer (use cases/hooks), not APIs directly"
    )


@pytest.mark.parametrize("ts_file", get_application_files())
def test_application_layer_has_no_jsx(ts_file):
    """
    SPEC-CODER-ARCH-PREACT-003: Application layer must not contain JSX

    GIVEN: TypeScript file in application layer (web/src/.../application/)
    WHEN: Checking file extension and content
    THEN: No .tsx files, no JSX syntax

    Rationale: Application layer orchestrates business logic, doesn't render UI
    """

    # Application should never use .tsx extension
    assert ts_file.suffix != ".tsx", (
        f"Application file {ts_file.relative_to(REPO_ROOT)} uses .tsx extension\n"
        f"Application layer orchestrates, doesn't render UI (use .ts)"
    )

    # Check for JSX syntax
    try:
        content = ts_file.read_text(encoding='utf-8')
    except Exception:
        return

    # JSX patterns (excluding TypeScript generics)
    jsx_patterns = [
        r'<[A-Z]\w+',           # Component tags: <Component
        r'</\w+>',              # Closing tags: </div>
        r'<\w+\s+\w+=',         # Tags with attributes: <div className=
        r'<\w+\s*/>',           # Self-closing tags: <div />
        r'<>\s*',               # Fragment: <>
        r'</>\s*',              # Fragment close: </>
    ]

    # TypeScript generic patterns to exclude
    ts_generic_patterns = [
        r'\bPromise<',
        r'\bArray<',
        r'\bRecord<',
        r'\bSet<',
        r'\bMap<',
        r'\bPartial<',
        r'\bReadonly<',
        r'\bOmit<',
        r'\bPick<',
        r'\bExtract<',
        r'\bExclude<',
        r'\bReturnType<',
        r'\bParameters<',
        r'\bcreateContext<',   # React/Preact createContext generic
        r'\buseState<',        # React/Preact useState generic
        r'\buseRef<',          # React/Preact useRef generic
        r'\buseMemo<',         # React/Preact useMemo generic
        r'\buseCallback<',     # React/Preact useCallback generic
    ]

    # Remove TypeScript generic patterns from content
    cleaned_content = content
    for pattern in ts_generic_patterns:
        cleaned_content = re.sub(pattern, '', cleaned_content)

    # Check for JSX in cleaned content
    has_jsx = any(re.search(pattern, cleaned_content) for pattern in jsx_patterns)

    assert not has_jsx, (
        f"Application file {ts_file.relative_to(REPO_ROOT)} contains JSX\n"
        f"Application layer should not render components"
    )


@pytest.mark.parametrize("test_file", get_test_files())
def test_component_tests_use_tsx_extension(test_file):
    """
    SPEC-CODER-ARCH-PREACT-004: Component tests must use .test.tsx

    GIVEN: Test file with 'render' from @testing-library
    WHEN: Checking file extension
    THEN: File has .tsx extension

    Rationale: Component tests with JSX should use .test.tsx for proper TypeScript handling
    """
    try:
        content = test_file.read_text(encoding='utf-8')
    except Exception:
        pytest.skip("Cannot read file")

    has_render = "from '@testing-library/preact'" in content
    # Match JSX tags (not TypeScript generics) - look for tags that start with uppercase or lowercase
    # JSX: <div>, <Component> | Not JSX: <string>, <Record<string, unknown>>
    has_jsx = bool(re.search(r'<[A-Z][a-zA-Z]*[\s/>]', content)) or bool(re.search(r'<[a-z]+[\s/>]', content))

    if has_render or has_jsx:
        assert test_file.suffix == ".tsx", (
            f"Test file {test_file.relative_to(REPO_ROOT)} uses component testing but has .ts extension\n"
            f"Component tests with JSX should use .test.tsx"
        )
