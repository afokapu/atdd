"""
Test and auto-fix URN headers in initialization/barrel files.

Validates and fixes:
- Python __init__.py files: URN comment + package docstring
- Dart index.dart files: URN comment + export documentation
- TypeScript index.ts files: URN comment + module documentation

Convention:
- All init/barrel files must have URN header
- URN format: urn:jel:{wagon}:{component}:{layer}:{sublayer}...
- URN derived from file path structure

Auto-fix Strategy:
- Generate URN from file path
- Add appropriate language-specific comment
- Add package/module docstring
- Preserve existing code (imports/exports)
"""

import pytest
import re
from pathlib import Path
from typing import List, Tuple, Optional


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "python"
DART_DIR = REPO_ROOT / "lib"
TS_DIR = REPO_ROOT / "typescript"


def find_python_init_files() -> List[Path]:
    """Find all Python __init__.py files."""
    if not PYTHON_DIR.exists():
        return []

    return list(PYTHON_DIR.rglob("__init__.py"))


def find_dart_index_files() -> List[Path]:
    """Find all Dart index.dart barrel files."""
    if not DART_DIR.exists():
        return []

    return list(DART_DIR.rglob("index.dart"))


def find_ts_index_files() -> List[Path]:
    """Find all TypeScript index.ts barrel files."""
    if not TS_DIR.exists():
        return []

    index_files = []
    index_files.extend(TS_DIR.rglob("index.ts"))
    index_files.extend(TS_DIR.rglob("index.tsx"))
    return index_files


def generate_urn_from_path(file_path: Path, language: str) -> str:
    """
    Generate URN from file path.

    Examples:
    - python/pace_dilemmas/pair_fragments/src/domain/services/__init__.py
      → urn:jel:pace-dilemmas:pair-fragments:domain:services

    - lib/maintain_ux/provide_foundations/index.dart
      → urn:jel:maintain-ux:provide-foundations

    - typescript/play_match/initialize_session/src/domain/index.ts
      → urn:jel:play-match:initialize-session:domain
    """
    parts = file_path.parts

    # Find language root index
    try:
        if language == "python":
            lang_idx = parts.index("python")
        elif language == "dart":
            lang_idx = parts.index("lib")
        elif language == "typescript":
            lang_idx = parts.index("typescript")
        else:
            return ""
    except ValueError:
        return ""

    # Extract path components after language root
    path_components = parts[lang_idx + 1:]

    # Remove filename and 'src' directories
    filtered_components = []
    for comp in path_components:
        if comp in ["__init__.py", "index.dart", "index.ts", "index.tsx"]:
            continue
        if comp == "src":
            continue
        # Convert underscores to hyphens for kebab-case
        comp_kebab = comp.replace("_", "-")
        filtered_components.append(comp_kebab)

    # Build URN
    if not filtered_components:
        return ""

    urn = "urn:jel:" + ":".join(filtered_components)
    return urn


def extract_urn_from_file(file_path: Path, language: str) -> Optional[str]:
    """Extract URN from file header."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return None

    comment_prefix = "#" if language == "python" else "//"

    for line in lines[:10]:  # Check first 10 lines
        stripped = line.strip()
        if stripped.startswith(comment_prefix):
            # Match: # urn:jel:... or // urn:jel:...
            match = re.match(rf'{re.escape(comment_prefix)}\s*urn:jel:(.+)', stripped)
            if match:
                return f"urn:jel:{match.group(1).strip()}"

    return None


def get_package_description(file_path: Path, urn: str) -> str:
    """Generate appropriate package description from URN."""
    # Extract last component as package name
    components = urn.split(":")
    if len(components) < 3:
        return "Package exports."

    last_component = components[-1]
    package_name = last_component.replace("-", "_")

    # Check if this is a layer name
    layer_names = {
        "domain": "Domain layer",
        "application": "Application layer",
        "presentation": "Presentation layer",
        "integration": "Integration layer",
        "entities": "Entity definitions",
        "services": "Domain services",
        "use-cases": "Use case implementations",
        "ports": "Port interfaces",
        "controllers": "Controller implementations",
        "repositories": "Repository implementations",
        "adapters": "Adapter implementations",
        "mappers": "Mapper implementations",
        "engines": "Engine implementations",
        "queries": "Query implementations",
        "validators": "Validator implementations",
    }

    if last_component in layer_names:
        return f"{layer_names[last_component]}."

    # Get parent component for context
    if len(components) >= 4:
        parent = components[-2]
        return f"{last_component.replace('-', ' ').title()} for {parent.replace('-', ' ')} component."

    return f"{package_name.replace('_', ' ').title()} package."


def fix_python_init_file(file_path: Path) -> bool:
    """
    Add URN header and docstring to Python __init__.py file.

    Returns:
        True if file was modified, False otherwise
    """
    # Generate expected URN
    expected_urn = generate_urn_from_path(file_path, "python")
    if not expected_urn:
        return False

    # Check current URN
    current_urn = extract_urn_from_file(file_path, "python")

    # Read current content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            current_content = f.read()
    except Exception:
        return False

    # Check if already has correct URN and docstring
    has_urn = current_urn == expected_urn
    has_docstring = '"""' in current_content or "'''" in current_content

    if has_urn and has_docstring:
        return False  # Already correct

    # Generate package description
    description = get_package_description(file_path, expected_urn)

    # Build new header
    header_parts = []

    # Add URN comment
    if not has_urn:
        header_parts.append(f"# {expected_urn}")

    # Add docstring
    if not has_docstring:
        header_parts.append(f'"""{description}"""')

    # Combine header with existing content
    if header_parts:
        # Remove old URN if exists
        lines = current_content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip old URN comments
            if line.strip().startswith("# urn:jel:"):
                continue
            cleaned_lines.append(line)

        cleaned_content = '\n'.join(cleaned_lines).lstrip('\n')

        new_content = '\n'.join(header_parts) + '\n'
        if cleaned_content:
            new_content += '\n' + cleaned_content

        # Write updated content
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        except Exception:
            return False

    return False


def fix_dart_index_file(file_path: Path) -> bool:
    """
    Add URN header and documentation to Dart index.dart file.

    Returns:
        True if file was modified, False otherwise
    """
    # Generate expected URN
    expected_urn = generate_urn_from_path(file_path, "dart")
    if not expected_urn:
        return False

    # Check current URN
    current_urn = extract_urn_from_file(file_path, "dart")

    # Read current content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            current_content = f.read()
    except Exception:
        return False

    # Check if already has correct URN
    if current_urn == expected_urn:
        return False  # Already correct

    # Generate module description
    description = get_package_description(file_path, expected_urn)

    # Build new header
    header = f"// {expected_urn}\n/// {description}\n"

    # Remove old URN if exists
    lines = current_content.split('\n')
    cleaned_lines = []
    for line in lines:
        # Skip old URN comments
        if line.strip().startswith("// urn:jel:"):
            continue
        # Skip old documentation comments at the start
        if not cleaned_lines and line.strip().startswith("///"):
            continue
        cleaned_lines.append(line)

    cleaned_content = '\n'.join(cleaned_lines).lstrip('\n')

    new_content = header
    if cleaned_content:
        new_content += '\n' + cleaned_content

    # Write updated content
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    except Exception:
        return False


def fix_ts_index_file(file_path: Path) -> bool:
    """
    Add URN header and documentation to TypeScript index.ts file.

    Returns:
        True if file was modified, False otherwise
    """
    # Generate expected URN
    expected_urn = generate_urn_from_path(file_path, "typescript")
    if not expected_urn:
        return False

    # Check current URN
    current_urn = extract_urn_from_file(file_path, "typescript")

    # Read current content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            current_content = f.read()
    except Exception:
        return False

    # Check if already has correct URN
    if current_urn == expected_urn:
        return False  # Already correct

    # Generate module description
    description = get_package_description(file_path, expected_urn)

    # Build new header
    header = f"// {expected_urn}\n/** {description} */\n"

    # Remove old URN if exists
    lines = current_content.split('\n')
    cleaned_lines = []
    for line in lines:
        # Skip old URN comments
        if line.strip().startswith("// urn:jel:"):
            continue
        cleaned_lines.append(line)

    cleaned_content = '\n'.join(cleaned_lines).lstrip('\n')

    new_content = header
    if cleaned_content:
        new_content += '\n' + cleaned_content

    # Write updated content
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    except Exception:
        return False


@pytest.mark.coder
def test_python_init_files_have_urns():
    """
    SPEC-CODER-URN-0001: Python __init__.py files have URN headers.

    All __init__.py files must have:
    - URN comment header (# urn:jel:...)
    - Package docstring

    Auto-fix: Adds missing URN and docstring

    Given: All Python __init__.py files
    When: Checking for URN headers
    Then: All files have correct URN and docstring
    """
    init_files = find_python_init_files()

    if not init_files:
        pytest.skip("No Python __init__.py files found")

    missing_urns = []
    fixed_files = []

    for init_file in init_files:
        expected_urn = generate_urn_from_path(init_file, "python")
        if not expected_urn:
            continue

        current_urn = extract_urn_from_file(init_file, "python")

        # Try to read content for docstring check
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                content = f.read()
            has_docstring = '"""' in content or "'''" in content
        except Exception:
            has_docstring = False

        if current_urn != expected_urn or not has_docstring:
            # Auto-fix
            if fix_python_init_file(init_file):
                fixed_files.append(init_file)
            else:
                missing_urns.append((init_file, expected_urn, current_urn))

    # Report results
    if fixed_files:
        rel_paths = [f.relative_to(REPO_ROOT) for f in fixed_files]
        print(f"\n✅ Auto-fixed {len(fixed_files)} Python __init__.py files:")
        for path in rel_paths[:10]:
            print(f"  {path}")
        if len(rel_paths) > 10:
            print(f"  ... and {len(rel_paths) - 10} more")

    if missing_urns:
        pytest.fail(
            f"\n\nFound {len(missing_urns)} Python __init__.py files that could not be fixed:\n\n" +
            "\n".join(
                f"  {file.relative_to(REPO_ROOT)}\n"
                f"    Expected: {expected}\n"
                f"    Current: {current or 'None'}"
                for file, expected, current in missing_urns[:10]
            ) +
            (f"\n\n... and {len(missing_urns) - 10} more" if len(missing_urns) > 10 else "")
        )


@pytest.mark.coder
def test_dart_index_files_have_urns():
    """
    SPEC-CODER-URN-0002: Dart index.dart files have URN headers.

    All index.dart barrel files must have:
    - URN comment header (// urn:jel:...)
    - Module documentation (///)

    Auto-fix: Adds missing URN and documentation

    Given: All Dart index.dart files
    When: Checking for URN headers
    Then: All files have correct URN and documentation
    """
    index_files = find_dart_index_files()

    if not index_files:
        pytest.skip("No Dart index.dart files found")

    missing_urns = []
    fixed_files = []

    for index_file in index_files:
        expected_urn = generate_urn_from_path(index_file, "dart")
        if not expected_urn:
            continue

        current_urn = extract_urn_from_file(index_file, "dart")

        if current_urn != expected_urn:
            # Auto-fix
            if fix_dart_index_file(index_file):
                fixed_files.append(index_file)
            else:
                missing_urns.append((index_file, expected_urn, current_urn))

    # Report results
    if fixed_files:
        rel_paths = [f.relative_to(REPO_ROOT) for f in fixed_files]
        print(f"\n✅ Auto-fixed {len(fixed_files)} Dart index.dart files:")
        for path in rel_paths[:10]:
            print(f"  {path}")
        if len(rel_paths) > 10:
            print(f"  ... and {len(rel_paths) - 10} more")

    if missing_urns:
        pytest.fail(
            f"\n\nFound {len(missing_urns)} Dart index.dart files that could not be fixed:\n\n" +
            "\n".join(
                f"  {file.relative_to(REPO_ROOT)}\n"
                f"    Expected: {expected}\n"
                f"    Current: {current or 'None'}"
                for file, expected, current in missing_urns[:10]
            ) +
            (f"\n\n... and {len(missing_urns) - 10} more" if len(missing_urns) > 10 else "")
        )


@pytest.mark.coder
def test_typescript_index_files_have_urns():
    """
    SPEC-CODER-URN-0003: TypeScript index.ts files have URN headers.

    All index.ts/tsx barrel files must have:
    - URN comment header (// urn:jel:...)
    - Module documentation (/** ... */)

    Auto-fix: Adds missing URN and documentation

    Given: All TypeScript index.ts/tsx files
    When: Checking for URN headers
    Then: All files have correct URN and documentation
    """
    index_files = find_ts_index_files()

    if not index_files:
        pytest.skip("No TypeScript index.ts/tsx files found")

    missing_urns = []
    fixed_files = []

    for index_file in index_files:
        expected_urn = generate_urn_from_path(index_file, "typescript")
        if not expected_urn:
            continue

        current_urn = extract_urn_from_file(index_file, "typescript")

        if current_urn != expected_urn:
            # Auto-fix
            if fix_ts_index_file(index_file):
                fixed_files.append(index_file)
            else:
                missing_urns.append((index_file, expected_urn, current_urn))

    # Report results
    if fixed_files:
        rel_paths = [f.relative_to(REPO_ROOT) for f in fixed_files]
        print(f"\n✅ Auto-fixed {len(fixed_files)} TypeScript index files:")
        for path in rel_paths[:10]:
            print(f"  {path}")
        if len(rel_paths) > 10:
            print(f"  ... and {len(rel_paths) - 10} more")

    if missing_urns:
        pytest.fail(
            f"\n\nFound {len(missing_urns)} TypeScript index files that could not be fixed:\n\n" +
            "\n".join(
                f"  {file.relative_to(REPO_ROOT)}\n"
                f"    Expected: {expected}\n"
                f"    Current: {current or 'None'}"
                for file, expected, current in missing_urns[:10]
            ) +
            (f"\n\n... and {len(missing_urns) - 10} more" if len(missing_urns) > 10 else "")
        )


@pytest.mark.coder
def test_urn_generation_logic():
    """
    SPEC-CODER-URN-0004: URN generation logic is correct.

    Validate URN generation from various file paths.

    Given: Sample file paths
    When: Generating URNs
    Then: URNs match expected format
    """
    test_cases = [
        # (file_path, language, expected_urn)
        ("python/pace_dilemmas/pair_fragments/src/domain/services/__init__.py",
         "python",
         "urn:jel:pace-dilemmas:pair-fragments:domain:services"),

        ("python/pace_dilemmas/pair_fragments/src/domain/__init__.py",
         "python",
         "urn:jel:pace-dilemmas:pair-fragments:domain"),

        ("lib/maintain_ux/provide_foundations/index.dart",
         "dart",
         "urn:jel:maintain-ux:provide-foundations"),

        ("typescript/play_match/initialize_session/src/domain/index.ts",
         "typescript",
         "urn:jel:play-match:initialize-session:domain"),
    ]

    failures = []

    for path_str, language, expected in test_cases:
        # Create a Path object from the string
        test_path = REPO_ROOT / path_str

        actual = generate_urn_from_path(test_path, language)

        if actual != expected:
            failures.append(
                f"Path: {path_str}\n"
                f"  Expected: {expected}\n"
                f"  Actual: {actual}"
            )

    if failures:
        pytest.fail(
            f"\n\nURN generation logic failures:\n\n" +
            "\n\n".join(failures)
        )
