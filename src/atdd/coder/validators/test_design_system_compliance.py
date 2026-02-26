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
import warnings
from pathlib import Path
from typing import List, Set, Dict, Tuple

from atdd.coach.utils.repo import find_repo_root


# Path constants
REPO_ROOT = find_repo_root()
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


def _get_maintain_ux_files(subdir: str) -> List[Path]:
    """Find all TS/TSX files under a maintain-ux subdirectory."""
    base = MAINTAIN_UX / subdir
    if not base.exists():
        return []
    files = []
    for ext in ("*.ts", "*.tsx"):
        for f in base.rglob(ext):
            if ".test." not in f.name and "/tests/" not in str(f):
                files.append(f)
    return files


@pytest.mark.coder
def test_design_system_hierarchy_imports():
    """
    SPEC-CODER-DESIGN-005: Design system layers must respect hierarchy.

    Implements VC-DS-03 through VC-DS-06 from design.convention.yaml.

    GIVEN: Files inside maintain-ux/{primitives,components,templates}
    WHEN: Analyzing their import paths
    THEN: No layer imports from a higher layer, and no maintain-ux file imports
          from feature wagons

    Hierarchy: tokens ← primitives ← components ← templates
    """
    primitives_files = _get_maintain_ux_files("primitives")
    components_files = _get_maintain_ux_files("components")
    all_ds_files = []
    if MAINTAIN_UX.exists():
        for ext in ("*.ts", "*.tsx"):
            for f in MAINTAIN_UX.rglob(ext):
                if ".test." not in f.name and "/tests/" not in str(f):
                    all_ds_files.append(f)

    if not primitives_files and not components_files and not all_ds_files:
        pytest.skip("No design system files found in maintain-ux/")

    violations = []

    # VC-DS-03: Primitives must not import from components or templates
    for f in primitives_files:
        imports = extract_imports(f)
        for imp in imports:
            if "../components/" in imp or "../components" == imp:
                rel = f.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel}\n"
                    f"  Forbidden: primitives → components (import '{imp}')\n"
                    f"  Fix: Primitives can only import from tokens"
                )
            if "../templates/" in imp or "../templates" == imp:
                rel = f.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel}\n"
                    f"  Forbidden: primitives → templates (import '{imp}')\n"
                    f"  Fix: Primitives can only import from tokens"
                )

    # VC-DS-04: Components must not import from templates
    for f in components_files:
        imports = extract_imports(f)
        for imp in imports:
            if "../templates/" in imp or "../templates" == imp:
                rel = f.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel}\n"
                    f"  Forbidden: components → templates (import '{imp}')\n"
                    f"  Fix: Components can import from tokens and primitives only"
                )

    # VC-DS-05 / VC-DS-06: No maintain-ux file imports from outside maintain-ux wagon paths
    for f in all_ds_files:
        imports = extract_imports(f)
        for imp in imports:
            # Skip relative imports within maintain-ux, node_modules, and bare specifiers
            if imp.startswith(".") or imp.startswith("@/maintain-ux"):
                continue
            if imp.startswith("preact") or imp.startswith("@preact"):
                continue
            # Flag imports that reach into other wagons
            if imp.startswith("@/") or imp.startswith("../"):
                # Reaching outside maintain-ux into a feature wagon
                rel = f.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel}\n"
                    f"  Forbidden: design system → wagon (import '{imp}')\n"
                    f"  Fix: Design system must be wagon-agnostic"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} hierarchy violations in design system:\n\n" +
            "\n\n".join(violations[:15]) +
            (f"\n\n... and {len(violations) - 15} more" if len(violations) > 15 else "") +
            "\n\nDesign system layers must follow: tokens ← primitives ← components ← templates"
        )


@pytest.mark.coder
def test_no_hardcoded_tokens_in_wagons():
    """
    SPEC-CODER-DESIGN-006: Wagon UI files must not use hardcoded spacing, radii, or durations.

    Extends DESIGN-002 (colors) to cover spacing, border-radius, and animation tokens.

    GIVEN: TSX files in web/src/ outside maintain-ux/
    WHEN: Scanning for inline pixel values, hardcoded radii, hardcoded durations
    THEN: No more than 20 violations (threshold for gradual migration)

    Rationale: All visual tokens must come from design system foundations
    """
    files = get_all_ui_files()
    if not files:
        pytest.skip("No frontend UI files found")

    all_violations = []

    # Patterns to detect hardcoded tokens (not colors — DESIGN-002 covers those)
    patterns = [
        # Inline pixel values in style objects: padding: "16px", margin: "24px", gap: "8px"
        (r'''(?:padding|margin|gap|top|bottom|left|right|width|height)\s*:\s*["'](\d+)px["']''',
         "Hardcoded pixel value in style string"),
        # Numeric px in template literals: `${16}px`
        (r"""\$\{\s*(\d+)\s*\}px""",
         "Hardcoded pixel value in template literal"),
        # Hardcoded border-radius as string: borderRadius: "8px"
        (r'''borderRadius\s*:\s*["'](\d+)px["']''',
         "Hardcoded border-radius string"),
        # Hardcoded border-radius as number: borderRadius: 8
        (r"""borderRadius\s*:\s*(\d+)\s*[,}\n]""",
         "Hardcoded border-radius number"),
        # Hardcoded transition durations: transition: "250ms", animationDuration: "300ms"
        (r'''(?:transition|animation(?:Duration)?)\s*:\s*["'][^"']*?(\d{2,})ms''',
         "Hardcoded duration"),
        # Raw numeric spacing in style props: padding: 16, margin: 24
        (r"""(?:padding|margin|gap)\s*:\s*(\d+)\s*[,}\n]""",
         "Hardcoded numeric spacing"),
    ]

    for f in files:
        try:
            content = f.read_text(encoding='utf-8')
        except Exception:
            continue

        lines = content.split('\n')
        file_violations = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip imports and comments
            if stripped.startswith('import') or stripped.startswith('//') or stripped.startswith('/*'):
                continue
            # Skip lines referencing design tokens
            if 'spacing.' in line or 'radii.' in line or 'motion.' in line or 'tokens.' in line:
                continue

            for pattern, description in patterns:
                for match in re.finditer(pattern, line):
                    value = int(match.group(1))
                    # Exclude values ≤ 4 (borders: 1px, 2px), 0 values
                    if value <= 4:
                        continue
                    file_violations.append((i, f"{description}: {match.group(0).strip()}"))

        if file_violations:
            rel_path = f.relative_to(REPO_ROOT)
            for line_num, issue in file_violations[:3]:  # Max 3 per file
                all_violations.append(
                    f"{rel_path}:{line_num}\n"
                    f"  {issue}\n"
                    f"  Fix: Use tokens from @/maintain-ux/foundations"
                )

    if len(all_violations) > 20:
        pytest.fail(
            f"\n\nFound {len(all_violations)} hardcoded token values (>20 threshold):\n\n" +
            "\n\n".join(all_violations[:10]) +
            (f"\n\n... and {len(all_violations) - 10} more" if len(all_violations) > 10 else "") +
            "\n\nUse spacing/radii/motion tokens from @/maintain-ux/foundations."
        )


@pytest.mark.coder
def test_no_orphaned_ui_elements():
    """
    SPEC-CODER-DESIGN-007: All TSX files must use at least one design system import.

    Unlike DESIGN-001 which only checks presentation/ layer, this validates ALL TSX files
    in web/src/ (pages, containers, layouts, any layer) are connected to the design system.

    GIVEN: Any .tsx file in web/src/ outside maintain-ux/ and test files
    WHEN: Checking its imports for any maintain-ux path
    THEN: File has at least one import from maintain-ux

    Rationale: Complete DS bypass means unthemed, inconsistent UI
    """
    files = get_all_ui_files()
    if not files:
        pytest.skip("No frontend UI files found")

    orphaned = []

    for f in files:
        try:
            content = f.read_text(encoding='utf-8')
        except Exception:
            continue

        # Only check files that actually render JSX
        if not re.search(r'return\s*\(?\s*<', content):
            continue

        imports = extract_imports(f)

        has_ds_import = any(
            'maintain-ux' in imp or '@maintain-ux' in imp
            for imp in imports
        )

        if not has_ds_import:
            rel_path = f.relative_to(REPO_ROOT)
            orphaned.append(
                f"{rel_path}\n"
                f"  Issue: TSX component with zero design system imports\n"
                f"  Fix: Import primitives/components from @/maintain-ux/"
            )

    if orphaned:
        pytest.fail(
            f"\n\nFound {len(orphaned)} orphaned UI elements (no design system imports):\n\n" +
            "\n\n".join(orphaned[:15]) +
            (f"\n\n... and {len(orphaned) - 15} more" if len(orphaned) > 15 else "") +
            "\n\nAll TSX files should use at least one design system import for consistency."
        )


@pytest.mark.coder
def test_design_system_metrics():
    """
    SPEC-CODER-DESIGN-008: Report design system adoption metrics.

    Reports 4 metrics from design.convention.yaml as informational warnings (never fails).

    Metrics:
      METRIC-DS-01: Coverage — wagons with DS imports / total wagons with TSX (target ≥ 80%)
      METRIC-DS-02: Reuse rate — avg times each DS export is imported (target ≥ 3)
      METRIC-DS-03: Hardcoded density — files with hardcoded values / total UI files (target < 5%)
      METRIC-DS-04: Hierarchy compliance — valid DS imports / total DS imports (target 100%)

    Rationale: Track design system health over time without blocking CI
    """
    ui_files = get_all_ui_files()
    if not ui_files:
        pytest.skip("No frontend UI files found")

    # --- METRIC-DS-01: Coverage ---
    # Group files by wagon (first directory under web/src/)
    wagons_with_tsx: Dict[str, bool] = {}
    for f in ui_files:
        try:
            rel = f.relative_to(WEB_SRC)
        except ValueError:
            continue
        wagon = rel.parts[0] if rel.parts else "root"
        imports = extract_imports(f)
        has_ds = any('maintain-ux' in imp or '@maintain-ux' in imp for imp in imports)
        if wagon not in wagons_with_tsx:
            wagons_with_tsx[wagon] = False
        if has_ds:
            wagons_with_tsx[wagon] = True

    total_wagons = len(wagons_with_tsx)
    ds_wagons = sum(1 for v in wagons_with_tsx.values() if v)
    coverage_pct = (ds_wagons / total_wagons * 100) if total_wagons > 0 else 0.0
    coverage_met = coverage_pct >= 80.0

    # --- METRIC-DS-02: Reuse rate ---
    exports = get_design_system_exports()
    all_exports = exports.get('primitives', set()) | exports.get('components', set()) | exports.get('foundations', set())
    usage_counts: Dict[str, int] = {name: 0 for name in all_exports}
    for f in ui_files:
        imported_names = extract_imported_names(f)
        for name, path in imported_names:
            if ('maintain-ux' in path or '@maintain-ux' in path) and name in usage_counts:
                usage_counts[name] += 1
    avg_reuse = (sum(usage_counts.values()) / len(usage_counts)) if usage_counts else 0.0
    reuse_met = avg_reuse >= 3.0

    # --- METRIC-DS-03: Hardcoded density ---
    files_with_hardcoded = 0
    for f in ui_files:
        color_violations = extract_raw_color_values(f)
        if color_violations:
            files_with_hardcoded += 1
    total_ui = len(ui_files)
    density_pct = (files_with_hardcoded / total_ui * 100) if total_ui > 0 else 0.0
    density_met = density_pct < 5.0

    # --- METRIC-DS-04: Hierarchy compliance ---
    total_ds_imports = 0
    valid_ds_imports = 0
    for f in ui_files:
        imports = extract_imports(f)
        for imp in imports:
            if 'maintain-ux' in imp or '@maintain-ux' in imp:
                total_ds_imports += 1
                if any(ds in imp for ds in DESIGN_SYSTEM_IMPORTS):
                    valid_ds_imports += 1
    hierarchy_pct = (valid_ds_imports / total_ds_imports * 100) if total_ds_imports > 0 else 100.0
    hierarchy_met = hierarchy_pct == 100.0

    # Emit all metrics as warnings (informational, never blocking)
    report = (
        f"\n--- Design System Metrics ---\n"
        f"METRIC-DS-01 Coverage:    {coverage_pct:5.1f}% ({ds_wagons}/{total_wagons} wagons)"
        f"  {'PASS' if coverage_met else 'BELOW TARGET'} (target ≥ 80%)\n"
        f"METRIC-DS-02 Reuse rate:  {avg_reuse:5.1f}x avg"
        f"  {'PASS' if reuse_met else 'BELOW TARGET'} (target ≥ 3)\n"
        f"METRIC-DS-03 Hardcoded:   {density_pct:5.1f}% ({files_with_hardcoded}/{total_ui} files)"
        f"  {'PASS' if density_met else 'ABOVE TARGET'} (target < 5%)\n"
        f"METRIC-DS-04 Hierarchy:   {hierarchy_pct:5.1f}% ({valid_ds_imports}/{total_ds_imports} imports)"
        f"  {'PASS' if hierarchy_met else 'BELOW TARGET'} (target 100%)\n"
    )
    warnings.warn(report, stacklevel=1)
