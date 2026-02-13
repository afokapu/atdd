"""
Test and auto-fix URN headers in initialization/barrel files.

Validates and fixes:
- Python __init__.py files: URN comment + package docstring
- Dart index.dart files: URN comment + export documentation
- TypeScript index.ts files: URN comment + module documentation

Convention:
- All init/barrel files must have a component URN header
- URN format: component:{wagon}:{feature}:{name}:{side}:{layer}
- URN derived from file path structure
- Header format: # URN: component:... (Python) or // URN: component:... (Dart/TS)

Auto-fix Strategy:
- Generate component URN from file path
- Add appropriate language-specific comment
- Add package/module docstring
- Preserve existing code (imports/exports)
"""

import pytest
import re
from pathlib import Path
from typing import List, Tuple, Optional

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.urn import URNBuilder


# Path constants
REPO_ROOT = find_repo_root()
PYTHON_DIR = REPO_ROOT / "python"
DART_DIR = REPO_ROOT / "lib"
TS_DIR = REPO_ROOT / "typescript"

# Standard URN comment pattern (matches # URN: ... or // URN: ...)
_URN_COMMENT_RE = re.compile(r"(?:#|//)\s*[Uu][Rr][Nn]:\s*([^\s]+)")


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
    Generate a component URN from an init/barrel file path.

    Maps file paths to component:{wagon}:{feature}:{name}:{side}:{layer}:

    - Wagon root (1 seg):     component:{wagon}:wagon:init:{side}:assembly
    - Feature root (2 seg):   component:{wagon}:{feature}:init:{side}:assembly
    - Layer init (3 seg):     component:{wagon}:{feature}:init:{side}:{layer}
    - Sublayer init (4+ seg): component:{wagon}:{feature}:{sublayer}:{side}:{layer}

    Examples:
    - python/pace_dilemmas/__init__.py
      -> component:pace-dilemmas:wagon:init:backend:assembly

    - python/pace_dilemmas/pair_fragments/src/domain/services/__init__.py
      -> component:pace-dilemmas:pair-fragments:services:backend:domain

    - lib/maintain_ux/provide_foundations/index.dart
      -> component:maintain-ux:provide-foundations:init:frontend:assembly

    - typescript/play_match/initialize_session/src/domain/index.ts
      -> component:play-match:initialize-session:init:frontend:domain
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

    # Determine side from language
    side = "backend" if language == "python" else "frontend"

    # Extract path components after language root
    path_components = parts[lang_idx + 1:]

    # Remove filename and 'src' directories, convert to kebab-case
    filtered = []
    for comp in path_components:
        if comp in ("__init__.py", "index.dart", "index.ts", "index.tsx"):
            continue
        if comp == "src":
            continue
        filtered.append(comp.replace("_", "-"))

    if not filtered:
        return ""

    # Map filtered segments to component URN fields
    seg_count = len(filtered)

    if seg_count == 1:
        # Wagon root: component:{wagon}:wagon:init:{side}:assembly
        wagon, feature, name, layer = filtered[0], "wagon", "init", "assembly"
    elif seg_count == 2:
        # Feature root: component:{wagon}:{feature}:init:{side}:assembly
        wagon, feature, name, layer = filtered[0], filtered[1], "init", "assembly"
    elif seg_count == 3:
        # Layer init: component:{wagon}:{feature}:init:{side}:{layer}
        wagon, feature, name, layer = filtered[0], filtered[1], "init", filtered[2]
    else:
        # Sublayer init (4+): component:{wagon}:{feature}:{last}:{side}:{layer_from_seg2}
        wagon, feature, name, layer = filtered[0], filtered[1], filtered[-1], filtered[2]

    urn = f"component:{wagon}:{feature}:{name}:{side}:{layer}"

    # Validate with URNBuilder before returning
    if not URNBuilder.validate_urn(urn, "component"):
        return ""

    return urn


def extract_urn_from_file(file_path: Path, language: str) -> Optional[str]:
    """Extract component URN from file header. Also detects legacy urn:jel: format."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return None

    comment_prefix = "#" if language == "python" else "//"

    for line in lines[:10]:  # Check first 10 lines
        stripped = line.strip()
        # Standard format: # URN: component:... or // URN: component:...
        m = _URN_COMMENT_RE.match(stripped)
        if m and m.group(1).startswith("component:"):
            return m.group(1)
        # Legacy format: # urn:jel:... or // urn:jel:...
        if stripped.startswith(f"{comment_prefix} urn:jel:"):
            return stripped[len(comment_prefix) + 1:]

    return None


def get_package_description(file_path: Path, urn: str) -> str:
    """Generate appropriate package description from component URN."""
    # component:{wagon}:{feature}:{name}:{side}:{layer}
    components = urn.split(":")
    if len(components) != 6:
        return "Package exports."

    name = components[3]
    layer = components[5]

    layer_names = {
        "domain": "Domain layer",
        "application": "Application layer",
        "presentation": "Presentation layer",
        "integration": "Integration layer",
        "assembly": "Package exports",
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

    # If the init is at layer/feature/wagon root, describe the layer
    if name == "init":
        if layer in layer_names:
            return f"{layer_names[layer]}."
        return "Package exports."

    # Sublayer: describe using known sublayer names or generic
    if name in layer_names:
        return f"{layer_names[name]}."

    feature = components[2]
    return f"{name.replace('-', ' ').title()} for {feature.replace('-', ' ')} component."


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
        header_parts.append(f"# URN: {expected_urn}")

    # Add docstring
    if not has_docstring:
        header_parts.append(f'"""{description}"""')

    # Combine header with existing content
    if header_parts:
        # Remove old URN if exists (both new and legacy formats)
        lines = current_content.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.strip().startswith("# URN: component:") or line.strip().startswith("# urn:jel:"):
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
    header = f"// URN: {expected_urn}\n/// {description}\n"

    # Remove old URN if exists (both new and legacy formats)
    lines = current_content.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith("// URN: component:") or line.strip().startswith("// urn:jel:"):
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
    header = f"// URN: {expected_urn}\n/** {description} */\n"

    # Remove old URN if exists (both new and legacy formats)
    lines = current_content.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith("// URN: component:") or line.strip().startswith("// urn:jel:"):
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
    - URN comment header (# URN: component:...)
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
    - URN comment header (// URN: component:...)
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
    - URN comment header (// URN: component:...)
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

    Validate URN generation from various file paths produces valid component URNs.

    Given: Sample file paths
    When: Generating URNs
    Then: URNs match expected component format and pass URNBuilder validation
    """
    test_cases = [
        # (file_path, language, expected_urn)
        ("python/pace_dilemmas/pair_fragments/src/domain/services/__init__.py",
         "python",
         "component:pace-dilemmas:pair-fragments:services:backend:domain"),

        ("python/pace_dilemmas/pair_fragments/src/domain/__init__.py",
         "python",
         "component:pace-dilemmas:pair-fragments:init:backend:domain"),

        ("lib/maintain_ux/provide_foundations/index.dart",
         "dart",
         "component:maintain-ux:provide-foundations:init:frontend:assembly"),

        ("typescript/play_match/initialize_session/src/domain/index.ts",
         "typescript",
         "component:play-match:initialize-session:init:frontend:domain"),

        ("python/pace_dilemmas/__init__.py",
         "python",
         "component:pace-dilemmas:wagon:init:backend:assembly"),

        ("python/pace_dilemmas/pair_fragments/__init__.py",
         "python",
         "component:pace-dilemmas:pair-fragments:init:backend:assembly"),
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

        # Validate generated URN passes component pattern
        if actual and not URNBuilder.validate_urn(actual, "component"):
            failures.append(
                f"Path: {path_str}\n"
                f"  URN failed validation: {actual}"
            )

    if failures:
        pytest.fail(
            f"\n\nURN generation logic failures:\n\n" +
            "\n\n".join(failures)
        )
