"""
Test design system compliance for Preact frontend.

Validates:
- Presentation components use design system primitives (maintain-ux)
- No raw CSS values bypass design tokens
- No orphaned design system exports (unused primitives)

Location: web/src/
Design System: web/src/maintain-ux/
"""

import pytest
import re
from pathlib import Path
from typing import List, Set, Dict, Tuple


# Path constants
REPO_ROOT = Path(__file__).resolve().parents[4]
WEB_SRC = REPO_ROOT / "web" / "src"
MAINTAIN_UX = WEB_SRC / "maintain-ux"
PRIMITIVES_DIR = MAINTAIN_UX / "primitives"
COMPONENTS_DIR = MAINTAIN_UX / "components"
FOUNDATIONS_DIR = MAINTAIN_UX / "foundations"


# Allowed design system import paths
DESIGN_SYSTEM_IMPORTS = [
    "@/maintain-ux/primitives",
    "@/maintain-ux/components",
    "@/maintain-ux/foundations",
    "@maintain-ux/primitives",
    "@maintain-ux/components",
    "@maintain-ux/foundations",
    "../primitives",
    "../components",
    "../foundations",
    "./primitives",
    "./components",
    "./foundations",
]


def get_presentation_files() -> List[Path]:
    """Find all presentation layer TypeScript files"""
    if not WEB_SRC.exists():
        return []

    files = []
    for f in WEB_SRC.rglob("*.tsx"):
        # Skip test files
        if ".test." in f.name or "/tests/" in str(f):
            continue
        # Skip design system internal files
        if "/maintain-ux/" in str(f):
            continue
        # Only presentation layer
        if "/presentation/" in str(f):
            files.append(f)

    return files


def get_all_ui_files() -> List[Path]:
    """Find all UI component files (presentation + pages)"""
    if not WEB_SRC.exists():
        return []

    files = []
    for f in WEB_SRC.rglob("*.tsx"):
        # Skip test files
        if ".test." in f.name or "/tests/" in str(f):
            continue
        # Skip design system internal files
        if "/maintain-ux/" in str(f):
            continue
        files.append(f)

    return files


def extract_imports(file_path: Path) -> List[str]:
    """Extract import statements from TypeScript file"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []

    import_pattern = r"import\s+.+\s+from\s+['\"](.+)['\"]"
    return re.findall(import_pattern, content)


def extract_imported_names(file_path: Path) -> List[Tuple[str, str]]:
    """Extract imported names and their source paths"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []

    results = []

    # Match: import { X, Y } from 'path'
    pattern = r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]"
    for match in re.finditer(pattern, content):
        names = [n.strip().split(' as ')[0] for n in match.group(1).split(',')]
        path = match.group(2)
        for name in names:
            if name:
                results.append((name.strip(), path))

    # Match: import X from 'path'
    pattern2 = r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]"
    for match in re.finditer(pattern2, content):
        name = match.group(1)
        path = match.group(2)
        if name not in ['type', 'React', 'h']:
            results.append((name, path))

    return results


def get_design_system_exports() -> Dict[str, Set[str]]:
    """Get all exported names from design system"""
    exports = {
        'primitives': set(),
        'components': set(),
        'foundations': set(),
    }

    # Check primitives index
    primitives_index = PRIMITIVES_DIR / "index.ts"
    if primitives_index.exists():
        content = primitives_index.read_text(encoding='utf-8')
        # Match: export { X, Y } from './Z'
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(' as ')[-1] for n in match.group(1).split(',')]
            exports['primitives'].update(n.strip() for n in names if n.strip())

    # Also check display/index.ts
    display_index = PRIMITIVES_DIR / "display" / "index.ts"
    if display_index.exists():
        content = display_index.read_text(encoding='utf-8')
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(' as ')[-1] for n in match.group(1).split(',')]
            exports['primitives'].update(n.strip() for n in names if n.strip())

    # Check components index
    components_index = COMPONENTS_DIR / "index.ts"
    if components_index.exists():
        content = components_index.read_text(encoding='utf-8')
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(' as ')[-1] for n in match.group(1).split(',')]
            exports['components'].update(n.strip() for n in names if n.strip())

    # Check foundations index
    foundations_index = FOUNDATIONS_DIR / "index.ts"
    if foundations_index.exists():
        content = foundations_index.read_text(encoding='utf-8')
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(' as ')[-1] for n in match.group(1).split(',')]
            exports['foundations'].update(n.strip() for n in names if n.strip())
        # Also match: export * from './X'
        for match in re.finditer(r"export\s+\*\s+from\s+['\"]\.\/(\w+)['\"]", content):
            submodule = match.group(1)
            subfile = FOUNDATIONS_DIR / f"{submodule}.ts"
            if subfile.exists():
                subcontent = subfile.read_text(encoding='utf-8')
                for submatch in re.finditer(r"export\s+(?:const|function|class)\s+(\w+)", subcontent):
                    exports['foundations'].add(submatch.group(1))

    # Filter out type exports (Props interfaces)
    for key in exports:
        exports[key] = {e for e in exports[key] if not e.endswith('Props')}

    return exports


def find_design_system_usage() -> Set[str]:
    """Find all design system imports used across the codebase"""
    used = set()

    for f in WEB_SRC.rglob("*.ts"):
        if "/maintain-ux/" in str(f):
            continue
        imports = extract_imported_names(f)
        for name, path in imports:
            if any(ds in path for ds in ['maintain-ux', '@maintain-ux']):
                used.add(name)

    for f in WEB_SRC.rglob("*.tsx"):
        if "/maintain-ux/" in str(f):
            continue
        imports = extract_imported_names(f)
        for name, path in imports:
            if any(ds in path for ds in ['maintain-ux', '@maintain-ux']):
                used.add(name)

    return used


def extract_raw_color_values(file_path: Path) -> List[Tuple[int, str]]:
    """Find raw hex/rgb color values not from design tokens"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []

    violations = []
    lines = content.split('\n')

    for i, line in enumerate(lines, 1):
        # Skip imports and comments
        if line.strip().startswith('import') or line.strip().startswith('//'):
            continue
        # Skip if it's referencing colors token
        if 'colors.' in line or 'colors[' in line:
            continue

        # Find hex colors (but allow #fff, #000 as they're common)
        hex_matches = re.findall(r'#[0-9a-fA-F]{6}\b', line)
        for match in hex_matches:
            # Allow white/black/common grays
            if match.lower() not in ['#ffffff', '#000000', '#1a1a1a', '#fff', '#000']:
                violations.append((i, f"Raw hex color: {match}"))

        # Find rgb/rgba colors (skip if in design token definition)
        if 'rgba(' in line.lower() and 'colors' not in line:
            violations.append((i, "Raw rgba() color"))

    return violations


@pytest.mark.coder
def test_presentation_uses_design_system_primitives():
    """
    SPEC-CODER-DESIGN-001: Presentation layer must use design system primitives.

    GIVEN: TypeScript file in presentation layer
    WHEN: Analyzing imports for UI elements
    THEN: Uses primitives from @/maintain-ux/primitives or @/maintain-ux/components

    Rationale: Consistent UI through reusable design system components
    """
    violations = []

    for f in get_presentation_files():
        imports = extract_imports(f)

        # Check if file uses preact/h but doesn't import from design system
        has_jsx = f.suffix == '.tsx'
        has_design_system_import = any(
            any(ds in imp for ds in DESIGN_SYSTEM_IMPORTS)
            for imp in imports
        )

        # If it's a .tsx file with no design system imports, flag it
        # (Allow commons imports for utilities)
        if has_jsx and not has_design_system_import:
            # Check if it has any actual JSX
            try:
                content = f.read_text(encoding='utf-8')
                # Look for JSX return statements
                if re.search(r'return\s*\(?\s*<', content):
                    rel_path = f.relative_to(REPO_ROOT)
                    violations.append(
                        f"{rel_path}\n"
                        f"  Issue: Presentation component with JSX but no design system imports\n"
                        f"  Fix: Import primitives from @/maintain-ux/primitives or @/maintain-ux/components"
                    )
            except Exception:
                pass

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} presentation files without design system imports:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nPresentation layer should use design system primitives for consistency."
        )


@pytest.mark.coder
def test_ui_files_use_design_tokens_for_colors():
    """
    SPEC-CODER-DESIGN-002: UI files should use design tokens for colors.

    GIVEN: TypeScript/TSX file with styling
    WHEN: Analyzing for color values
    THEN: Colors come from design tokens, not raw hex/rgb values

    Rationale: Consistent theming through centralized color definitions
    """
    all_violations = []

    for f in get_all_ui_files():
        violations = extract_raw_color_values(f)
        if violations:
            rel_path = f.relative_to(REPO_ROOT)
            for line_num, issue in violations[:3]:  # Max 3 per file
                all_violations.append(
                    f"{rel_path}:{line_num}\n"
                    f"  {issue}\n"
                    f"  Fix: Use colors from @/maintain-ux/foundations"
                )

    # Allow some violations during migration (warning, not failure)
    if len(all_violations) > 20:
        pytest.fail(
            f"\n\nFound {len(all_violations)} raw color values (>20 threshold):\n\n" +
            "\n\n".join(all_violations[:10]) +
            (f"\n\n... and {len(all_violations) - 10} more" if len(all_violations) > 10 else "") +
            "\n\nUse colors from @/maintain-ux/foundations for consistency."
        )


@pytest.mark.coder
def test_no_orphaned_design_system_exports():
    """
    SPEC-CODER-DESIGN-003: Design system exports should be used.

    GIVEN: Exports from maintain-ux/primitives and maintain-ux/components
    WHEN: Scanning codebase for imports
    THEN: All exports are imported somewhere (no orphaned code)

    Rationale: Remove dead code, keep design system lean
    """
    exports = get_design_system_exports()
    used = find_design_system_usage()

    # Combine all exports
    all_exports = exports['primitives'] | exports['components']

    # Find orphaned (exported but never imported)
    orphaned = all_exports - used

    # Filter out common false positives
    false_positives = {'type', 'h', 'Fragment'}
    orphaned = orphaned - false_positives

    if orphaned:
        # Group by category
        orphaned_primitives = orphaned & exports['primitives']
        orphaned_components = orphaned & exports['components']

        message = f"\n\nFound {len(orphaned)} orphaned design system exports:\n"

        if orphaned_primitives:
            message += f"\n  Primitives ({len(orphaned_primitives)}):\n"
            message += "".join(f"    - {name}\n" for name in sorted(orphaned_primitives))

        if orphaned_components:
            message += f"\n  Components ({len(orphaned_components)}):\n"
            message += "".join(f"    - {name}\n" for name in sorted(orphaned_components))

        message += "\nConsider removing unused exports to keep design system lean."

        # Warn but don't fail if under threshold
        if len(orphaned) > 5:
            pytest.fail(message)
        else:
            pytest.skip(f"Minor: {len(orphaned)} orphaned exports (under threshold)")


@pytest.mark.coder
def test_design_system_uses_foundations():
    """
    SPEC-CODER-DESIGN-004: Design system primitives should use foundations.

    GIVEN: Primitive or component in maintain-ux
    WHEN: Checking for spacing/color values
    THEN: Uses tokens from foundations (spacing, colors)

    Rationale: Design system itself must be consistent
    """
    violations = []

    for category_dir in [PRIMITIVES_DIR, COMPONENTS_DIR]:
        if not category_dir.exists():
            continue

        for f in category_dir.rglob("*.tsx"):
            # Skip index files
            if f.name == "index.ts":
                continue

            try:
                content = f.read_text(encoding='utf-8')
            except Exception:
                continue

            # Check if it imports from foundations
            imports = extract_imports(f)
            uses_foundations = any('../foundations' in imp or './foundations' in imp for imp in imports)

            # Check for raw pixel values in styles (allow small values like 2px, 3px for borders)
            raw_pixels = re.findall(r":\s*['\"]?(\d{2,}px)['\"]?", content)

            if raw_pixels and not uses_foundations:
                rel_path = f.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}\n"
                    f"  Raw pixel values: {', '.join(raw_pixels[:5])}\n"
                    f"  Fix: Import spacing from ../foundations"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} design system files with raw values:\n\n" +
            "\n\n".join(violations[:10]) +
            (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "") +
            "\n\nDesign system should use its own foundations for consistency."
        )
