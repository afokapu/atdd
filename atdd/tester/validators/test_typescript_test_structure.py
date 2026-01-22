"""
Platform tests: TypeScript test structure validation.

Focuses on URN headers and TSX usage for component tests under web/tests/.
"""
import pytest
import re


URN_HEADER_PATTERN = re.compile(
    r'^//\s*(?:URN|urn):\s*(acc:[a-z][a-z0-9-]*:[A-Z][0-9]{3}-[A-Z0-9]+-[0-9]{3}(?:-[a-z0-9-]+)?)$'
)


@pytest.mark.platform
def test_typescript_test_files_have_urn_header(web_typescript_test_files):
    """
    SPEC-TESTER-TS-001: All TypeScript test files must have URN header.
    """
    errors = []

    for test_file in web_typescript_test_files:
        lines = test_file.read_text().splitlines()
        first_non_empty = next((line.strip() for line in lines if line.strip()), "")

        if not URN_HEADER_PATTERN.match(first_non_empty):
            errors.append(
                f"❌ {test_file}\n"
                f"   Missing URN header in first non-empty line.\n"
                f"   Expected: // URN: acc:{{wagon}}:{{WMBT}}-{{HARNESS}}-{{NNN}}[-slug]"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test files missing URN headers:\n\n" +
            "\n".join(errors)
        )


@pytest.mark.platform
def test_component_tests_use_tsx_extension(web_typescript_test_files):
    """
    SPEC-TESTER-TS-002: Component tests using JSX must use .test.tsx.
    """
    errors = []

    for test_file in web_typescript_test_files:
        content = test_file.read_text()
        has_render = "from '@testing-library/preact'" in content
        has_jsx = bool(re.search(r'<\\w+.*?>', content))

        if (has_render or has_jsx) and not test_file.name.endswith(".test.tsx"):
            errors.append(
                f"❌ {test_file}\n"
                f"   Component test uses JSX but is not .test.tsx"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 Component tests must use .test.tsx:\n\n" +
            "\n".join(errors)
        )


@pytest.mark.platform
def test_preact_test_files_use_urn_filename_format(web_typescript_test_files):
    """
    SPEC-TESTER-TS-003: Preact TypeScript tests use URN-based filename format.
    """
    pattern = re.compile(r'^([A-Z][0-9]{3})_([A-Z0-9]+)_([0-9]{3})(?:_([a-z0-9_]+))?\.test\.ts(x)?$')
    errors = []

    for test_file in web_typescript_test_files:
        if not pattern.match(test_file.name):
            errors.append(
                f"❌ {test_file}\n"
                f"   Expected: C004_UNIT_001_slug.test.ts[x]"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 Preact TypeScript tests use invalid filenames:\n\n" +
            "\n".join(errors)
        )
