"""
Platform tests: TypeScript test file naming validation.

Validates that all TypeScript test files conform to Node.js/TypeScript naming conventions.
Tests parametrized to run once per test file for surgical diagnostics.

Migration Note:
  Legacy format: ac-{type}-{nnn}.{purpose-slug}.test.ts (uses acceptance ID)
  New format: {wmbt_lower}-{harness_lower}-{nnn}[-{slug-kebab}].test.ts (uses URN)

  New URN-based naming documented in:
    - .claude/conventions/tester/filename.convention.yaml
    - atdd.tester.utils.filename module
    - SPEC-TESTER-CONV-0070

  See test_acceptance_urn_filename_mapping.py for validation of new format.
"""
import pytest
import re
from pathlib import Path


@pytest.mark.platform
def test_typescript_test_files_use_kebab_case(typescript_test_files):
    """
    SPEC-PLATFORM-TS-0001: TypeScript test files use kebab-case naming

    Given: TypeScript test files in supabase/ and e2e/ directories
    When: Checking file naming conventions
    Then: All test files use kebab-case (lowercase with hyphens)
          No underscores allowed in filenames (except in .test.ts suffix)
          Pattern: {normalized_id}.{purpose_slug}.test.ts

    Convention: atdd/tester/conventions/red.convention.yaml:254-285
    """
    errors = []

    for test_file in typescript_test_files:
        filename = test_file.name

        # Remove .test.ts suffix
        base_name = filename.replace('.test.ts', '')

        # Check for invalid characters (underscores)
        if '_' in base_name:
            errors.append(
                f"❌ {test_file.relative_to(Path.cwd())}\n"
                f"   Contains underscores. Expected kebab-case format.\n"
                f"   Example: ac-http-006.primitive-endpoint.test.ts"
            )

        # Check for uppercase letters
        if base_name != base_name.lower():
            errors.append(
                f"❌ {test_file.relative_to(Path.cwd())}\n"
                f"   Contains uppercase letters. Expected all lowercase.\n"
                f"   Example: ac-db-015.user-records-persist.test.ts"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test files violate Node.js naming conventions:\n\n" +
            "\n".join(errors) +
            "\n\n📘 See: atdd/tester/conventions/red.convention.yaml:254-285"
        )


@pytest.mark.platform
def test_typescript_test_files_match_acceptance_pattern(typescript_test_files):
    """
    SPEC-PLATFORM-TS-0002: TypeScript test files follow acceptance-derived naming

    Given: TypeScript test files in supabase/ and e2e/ directories
    When: Checking naming pattern
    Then: Files match pattern: {normalized_id}.{purpose_slug}.test.ts
          normalized_id: AC-HTTP-006 → ac-http-006 (kebab-case)
          purpose_slug: extracted from identity.purpose field (kebab-case)

    Convention: atdd/tester/conventions/red.convention.yaml:254-285
    """
    # Pattern: {normalized_id}.{purpose_slug}.test.ts
    # normalized_id: ac-http-006, ac-db-015, etc.
    # purpose_slug: primitive-endpoint, user-records-persist, etc.

    valid_pattern = re.compile(r'^ac-[a-z]+-\d{3}\.[a-z][a-z0-9-]*\.test\.ts$')
    errors = []

    for test_file in typescript_test_files:
        filename = test_file.name

        if not valid_pattern.match(filename):
            errors.append(
                f"❌ {test_file.relative_to(Path.cwd())}\n"
                f"   Pattern mismatch. Expected: ac-{{type}}-{{nnn}}.{{purpose}}.test.ts\n"
                f"   Example: ac-http-006.primitive-endpoint.test.ts"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test files don't match expected pattern:\n\n" +
            "\n".join(errors) +
            "\n\n📘 Pattern: ac-{type}-{nnn}.{purpose}.test.ts\n" +
            "📘 See: atdd/tester/conventions/red.convention.yaml:254-285"
        )


@pytest.mark.platform
def test_typescript_test_files_have_urn_comment(typescript_test_files):
    """
    SPEC-PLATFORM-TS-0003: TypeScript test files contain URN comment

    Given: TypeScript test files in supabase/ and e2e/ directories
    When: Reading file contents
    Then: First line contains URN comment in format:
          // urn: acc:{wagon}.{wmbt}.{acceptance_id}

    Example: // urn: acc:maintain-ux.P002.AC-HTTP-006
    """
    errors = []

    for test_file in typescript_test_files:
        with open(test_file, 'r') as f:
            first_line = f.readline().strip()

        # Check for URN comment pattern
        urn_pattern = re.compile(r'^// urn: acc:[a-z][a-z0-9-]+\.[A-Z]\d{3}\.AC-[A-Z]+-\d{3}$')

        if not urn_pattern.match(first_line):
            errors.append(
                f"❌ {test_file.relative_to(Path.cwd())}\n"
                f"   Missing or invalid URN comment in first line.\n"
                f"   Found: {first_line[:80]}\n"
                f"   Expected: // urn: acc:{{wagon}}.{{wmbt}}.{{acceptance_id}}"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test files missing URN comments:\n\n" +
            "\n".join(errors) +
            "\n\n📘 First line must be: // urn: acc:{wagon}.{wmbt}.{acceptance_id}"
        )


@pytest.mark.platform
def test_typescript_test_files_organized_by_wagon(typescript_test_files):
    """
    SPEC-PLATFORM-TS-0004: TypeScript test files organized by wagon

    Given: TypeScript test files in supabase/ and e2e/ directories
    When: Checking directory structure
    Then: Backend tests: supabase/functions/{wagon}/test/{test_file}.test.ts
          E2E tests: e2e/{wagon}/{test_file}.test.ts

    Example: supabase/functions/maintain-ux/test/ac-http-006.primitive-endpoint.test.ts
    """
    errors = []

    for test_file in typescript_test_files:
        parts = test_file.parts

        # Check if it's a supabase backend test
        if 'supabase' in parts and 'functions' in parts:
            try:
                supabase_idx = parts.index('supabase')
                functions_idx = parts.index('functions')

                # Expected: supabase/functions/{wagon}/test/{file}.test.ts
                if functions_idx != supabase_idx + 1:
                    errors.append(
                        f"❌ {test_file.relative_to(Path.cwd())}\n"
                        f"   Invalid structure. Expected: supabase/functions/{{wagon}}/test/{{file}}.test.ts"
                    )
                    continue

                remaining = parts[functions_idx + 1:]
                # Should have: wagon/test/file.test.ts
                if len(remaining) < 3 or remaining[1] != 'test':
                    errors.append(
                        f"❌ {test_file.relative_to(Path.cwd())}\n"
                        f"   Not in test/ subdirectory.\n"
                        f"   Expected: supabase/functions/{{wagon}}/test/{{file}}.test.ts"
                    )
            except (ValueError, IndexError):
                errors.append(
                    f"❌ {test_file.relative_to(Path.cwd())}\n"
                    f"   Invalid supabase structure"
                )

        # Check if it's an e2e test
        elif 'e2e' in parts:
            try:
                e2e_idx = parts.index('e2e')
                remaining = parts[e2e_idx + 1:]

                # Should have at least: wagon/file.test.ts
                if len(remaining) < 2:
                    errors.append(
                        f"❌ {test_file.relative_to(Path.cwd())}\n"
                        f"   Not organized by wagon.\n"
                        f"   Expected: e2e/{{wagon}}/{{file}}.test.ts"
                    )
            except (ValueError, IndexError):
                errors.append(
                    f"❌ {test_file.relative_to(Path.cwd())}\n"
                    f"   Invalid e2e structure"
                )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test files not properly organized:\n\n" +
            "\n".join(errors) +
            "\n\n📘 Backend: supabase/functions/{wagon}/test/{file}.test.ts\n" +
            "📘 E2E: e2e/{wagon}/{file}.test.ts"
        )


@pytest.mark.platform
def test_typescript_test_filename_matches_urn_acceptance_id(typescript_test_files):
    """
    SPEC-PLATFORM-TS-0005: Test filename normalized_id matches URN acceptance_id

    Given: TypeScript test files with URN comments
    When: Comparing filename normalized_id to URN acceptance_id
    Then: normalized_id matches acceptance_id (converted to kebab-case)
          Example: ac-http-006 matches AC-HTTP-006

    Convention: atdd/tester/conventions/red.convention.yaml:255-260
    """
    errors = []

    for test_file in typescript_test_files:
        # Read URN from first line
        with open(test_file, 'r') as f:
            first_line = f.readline().strip()

        # Extract acceptance_id from URN (e.g., AC-HTTP-006)
        urn_match = re.search(r'// urn: acc:[a-z][a-z0-9-]+\.[A-Z]\d{3}\.(AC-[A-Z]+-\d{3})', first_line)

        if not urn_match:
            continue  # Skip if URN not found (covered by other test)

        acceptance_id = urn_match.group(1)  # e.g., AC-HTTP-006

        # Normalize acceptance_id to kebab-case
        expected_normalized_id = acceptance_id.lower()  # ac-http-006

        # Extract normalized_id from filename (first part before purpose_slug)
        filename = test_file.name
        # Pattern: {normalized_id}.{purpose_slug}.test.ts
        parts = filename.replace('.test.ts', '').split('.')

        if len(parts) >= 1:
            actual_normalized_id = parts[0]  # ac-http-006

            if actual_normalized_id != expected_normalized_id:
                errors.append(
                    f"❌ {test_file.relative_to(Path.cwd())}\n"
                    f"   Filename normalized_id doesn't match URN acceptance_id.\n"
                    f"   URN acceptance_id: {acceptance_id}\n"
                    f"   Expected normalized: {expected_normalized_id}\n"
                    f"   Actual in filename: {actual_normalized_id}"
                )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test filenames don't match URN acceptance IDs:\n\n" +
            "\n".join(errors) +
            "\n\n📘 Transformation: AC-HTTP-006 → ac-http-006\n" +
            "📘 See: atdd/tester/conventions/red.convention.yaml:255-260"
        )


@pytest.mark.platform
def test_typescript_test_files_use_correct_extension(typescript_test_files):
    """
    SPEC-PLATFORM-TS-0006: TypeScript test files use .test.ts extension

    Given: TypeScript test files in supabase/ and e2e/ directories
    When: Checking file extensions
    Then: Files use .test.ts
          No other extensions allowed

    Convention: Standard Node.js/TypeScript testing convention
    """
    errors = []

    for test_file in typescript_test_files:
        filename = test_file.name

        if not filename.endswith('.test.ts'):
            errors.append(
                f"❌ {test_file.relative_to(Path.cwd())}\n"
                f"   Invalid extension. Expected: .test.ts"
            )

    if errors:
        pytest.fail(
            "\n\n🔴 TypeScript test files have invalid extensions:\n\n" +
            "\n".join(errors) +
            "\n\n📘 Use .test.ts"
        )
