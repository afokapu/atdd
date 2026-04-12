"""
Test wagon boundary isolation for TypeScript imports.

Validates conventions from:
- atdd/coder/conventions/boundaries.convention.yaml

Enforces:
- No direct cross-wagon internal path imports (bypassing barrel exports)
- Cross-wagon access must go through barrel exports (index.ts)
- Composition roots are exempt (they wire dependencies)

Rationale:
Frontend wagons under web/src/ follow the pattern:
    web/src/{wagon}/{feature}/{layer}/{module}.ts

A file in wagon A importing directly into wagon B's internals
(e.g., `@/wagon-b/feature/domain/entity`) creates tight coupling.
Cross-wagon access should use barrel exports:
    import { Entity } from '@/wagon-b/feature'  // index.ts barrel

This is the TypeScript parity of test_wagon_boundaries.py which enforces
the same pattern for Python wagons.

Hard-fail: no ratchet baseline — violations must be zero.
"""

import os
import re
import pytest
from pathlib import Path
from typing import List, Optional, Set, Tuple

from atdd.coach.utils.repo import find_repo_root

import atdd


# ============================================================================
# PATH CONSTANTS
# ============================================================================

REPO_ROOT = find_repo_root()
WEB_SRC = REPO_ROOT / "web" / "src"
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
BOUNDARIES_CONVENTION = ATDD_PKG_DIR / "coder" / "conventions" / "boundaries.convention.yaml"

_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".cache",
}

_TS_EXTENSIONS = {".ts", ".tsx"}

# Architectural layers in the 4-layer convention
_LAYERS = {"domain", "application", "integration", "presentation"}

# Files that are composition roots — exempt from boundary checks
# (they wire dependencies and may legitimately reach across wagons)
_COMPOSITION_FILENAMES = {
    "composition.ts", "composition.tsx",
    "wagon.ts", "wagon.tsx",
    "main.ts", "main.tsx",
    "app.ts", "app.tsx",
}


# ============================================================================
# FILE DISCOVERY
# ============================================================================


def find_implementation_files() -> List[Path]:
    """
    Find all implementation files in web/src/ wagons.

    Excludes:
    - Test files (.test.ts, .spec.ts)
    - Barrel exports (index.ts — neutral boundary layer)
    - Composition roots (composition.ts, wagon.ts, app entry points)
    - Files in test/tests/__tests__ directories
    """
    if not WEB_SRC.exists():
        return []

    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(WEB_SRC):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        # Skip test directories
        if any(part in {"test", "tests", "__tests__"} for part in Path(dirpath).parts):
            continue

        for fname in filenames:
            if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                continue
            # Skip test files
            if any(fname.endswith(p) for p in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            # Skip barrel exports (neutral boundary layer)
            if fname in {"index.ts", "index.tsx"}:
                continue
            # Skip composition roots
            if fname in _COMPOSITION_FILENAMES:
                continue

            files.append(Path(dirpath) / fname)

    return sorted(files)


# ============================================================================
# WAGON / IMPORT ANALYSIS
# ============================================================================


def get_wagon_from_path(file_path: Path) -> Optional[str]:
    """
    Extract wagon name from a web/src/ file path.

    Pattern: web/src/{wagon}/{feature}/{layer}/{module}.ts
    Returns the first directory component under web/src/.
    """
    try:
        rel = file_path.relative_to(WEB_SRC)
        parts = rel.parts
        if parts:
            return parts[0]
    except ValueError:
        pass
    return None


def extract_imports(file_path: Path) -> List[Tuple[str, int]]:
    """
    Extract import specifiers and line numbers from a TypeScript file.

    Returns:
        List of (import_specifier, line_number) tuples.
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    imports: List[Tuple[str, int]] = []

    # Pattern: import ... from 'path'  or  export ... from 'path'
    import_re = re.compile(
        r"""(?:import|export)\s+"""
        r"""(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]"""
    )

    for i, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith(("import ", "export ")):
            continue
        match = import_re.match(stripped)
        if match:
            imports.append((match.group(1), i))

    return imports


def is_cross_wagon_internal_import(
    file_path: Path,
    specifier: str,
) -> Tuple[bool, str, str, str]:
    """
    Check if an import specifier crosses wagon boundaries via internal path.

    A cross-wagon internal import is one that:
    1. Targets a different wagon than the source file
    2. Reaches into the wagon's internal structure (past the barrel)
       e.g., @/other-wagon/feature/domain/entity (3+ segments past wagon)

    Allowed:
    - @/other-wagon/feature (stops at barrel — index.ts)
    - ./relative/within/same/wagon
    - External packages

    Returns:
        (is_violation, source_wagon, target_wagon, specifier)
    """
    source_wagon = get_wagon_from_path(file_path)
    if not source_wagon:
        return (False, "", "", specifier)

    # Only check path-alias imports that resolve to web/src/
    if not specifier.startswith("@/"):
        return (False, source_wagon, "", specifier)

    # Parse the import path: @/{wagon}/{feature}/{layer}/...
    remainder = specifier[2:]  # strip '@/'
    parts = remainder.split("/")

    if not parts:
        return (False, source_wagon, "", specifier)

    target_wagon = parts[0]

    # Same wagon — not a cross-wagon import
    if target_wagon == source_wagon:
        return (False, source_wagon, target_wagon, specifier)

    # Cross-wagon import — check if it reaches into internals
    # @/{wagon}/{feature} → 2 parts → barrel-level (OK)
    # @/{wagon}/{feature}/{layer}/... → 3+ parts → internal path (VIOLATION)
    if len(parts) <= 2:
        # Stops at wagon or wagon/feature barrel — allowed
        return (False, source_wagon, target_wagon, specifier)

    # 3+ segments: check if the third segment is a layer name
    if len(parts) >= 3 and parts[2] in _LAYERS:
        return (True, source_wagon, target_wagon, specifier)

    # 3+ segments with non-layer third segment could still be internal
    # e.g., @/other-wagon/feature/utils/helper — still bypasses barrel
    # Check if the target resolves to actual files under web/src/
    target_dir = WEB_SRC / "/".join(parts[:2])
    if target_dir.is_dir() and len(parts) >= 3:
        # Importing 3+ segments into another wagon's directory = internal access
        return (True, source_wagon, target_wagon, specifier)

    return (False, source_wagon, target_wagon, specifier)


# ============================================================================
# SCAN FUNCTION (for baseline.py registry)
# ============================================================================


def scan_wagon_boundaries_typescript(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for cross-wagon internal imports. Used by ratchet baseline."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    # Collect implementation files (reuse logic but with custom root)
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(web_src):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if any(part in {"test", "tests", "__tests__"} for part in Path(dirpath).parts):
            continue
        for fname in filenames:
            if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                continue
            if any(fname.endswith(p) for p in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            if fname in {"index.ts", "index.tsx"}:
                continue
            if fname in _COMPOSITION_FILENAMES:
                continue
            files.append(Path(dirpath) / fname)

    violations: List[str] = []
    for impl_file in files:
        imports = extract_imports(impl_file)
        for specifier, line_no in imports:
            is_violation, src_wagon, tgt_wagon, spec = is_cross_wagon_internal_import(
                impl_file, specifier
            )
            if is_violation:
                try:
                    rel_path = impl_file.relative_to(repo_root)
                except ValueError:
                    rel_path = impl_file
                violations.append(
                    f"{rel_path}:{line_no} [{src_wagon} → {tgt_wagon}] {spec}"
                )

    return len(violations), violations


# ============================================================================
# TEST FUNCTIONS
# ============================================================================


@pytest.mark.coder
def test_no_cross_wagon_internal_imports():
    """
    SPEC-BOUNDARIES-TS-0001: No direct cross-wagon internal path imports.

    Convention: boundaries.convention.yaml::interaction.forbidden_cross_wagon_imports

    Forbidden:
    - import { Entity } from '@/other-wagon/feature/domain/entity'
    - import { Repo } from '@/other-wagon/feature/integration/repo'

    Required:
    - import { Entity } from '@/other-wagon/feature'  (barrel export)

    Cross-wagon access MUST go through barrel exports (index.ts).
    Reaching into another wagon's layer directory creates tight coupling
    and breaks independent evolution.

    Hard-fail: violations must be zero (no baseline).

    Given: All implementation files in web/src/
    When: Checking imports for cross-wagon internal paths
    Then: No imports bypass barrel exports into other wagons' internals

    BE parity: test_wagon_boundaries.py::test_no_cross_wagon_imports
    """
    impl_files = find_implementation_files()

    if not impl_files:
        pytest.skip("No implementation files found in web/src/ to validate")

    violations: List[str] = []

    for impl_file in impl_files:
        imports = extract_imports(impl_file)

        for specifier, line_no in imports:
            is_violation, src_wagon, tgt_wagon, spec = is_cross_wagon_internal_import(
                impl_file, specifier
            )

            if is_violation:
                rel_path = impl_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Source wagon: {src_wagon}\n"
                    f"  Target wagon: {tgt_wagon}\n"
                    f"  Import: {spec}\n"
                    f"  Issue: Direct cross-wagon internal import bypasses barrel export\n"
                    f"  Fix: import from '@/{tgt_wagon}/{{feature}}' (barrel) instead"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} cross-wagon internal imports:\n\n"
            + "\n\n".join(violations[:10])
            + (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
            + "\n\nCross-wagon access must go through barrel exports (index.ts)."
            + "\nSee: atdd/coder/conventions/boundaries.convention.yaml::interaction"
        )


@pytest.mark.coder
def test_no_relative_cross_wagon_imports():
    """
    SPEC-BOUNDARIES-TS-0002: No relative imports that escape wagon boundaries.

    Forbidden:
    - import { X } from '../../other-wagon/feature/domain/entity'

    Relative imports that traverse up past the wagon root and into another
    wagon's directory are boundary violations.

    Given: All implementation files in web/src/
    When: Checking relative imports for wagon boundary escapes
    Then: No relative imports cross wagon boundaries
    """
    impl_files = find_implementation_files()

    if not impl_files:
        pytest.skip("No implementation files found in web/src/ to validate")

    violations: List[str] = []

    for impl_file in impl_files:
        source_wagon = get_wagon_from_path(impl_file)
        if not source_wagon:
            continue

        imports = extract_imports(impl_file)

        for specifier, line_no in imports:
            if not specifier.startswith(".."):
                continue

            # Resolve the relative import to an absolute path
            resolved = (impl_file.parent / specifier).resolve()
            try:
                rel_to_src = resolved.relative_to(WEB_SRC.resolve())
                target_wagon = rel_to_src.parts[0] if rel_to_src.parts else None
            except ValueError:
                continue  # Resolves outside web/src/ — not our concern

            if target_wagon and target_wagon != source_wagon:
                rel_path = impl_file.relative_to(REPO_ROOT)
                violations.append(
                    f"{rel_path}:{line_no}\n"
                    f"  Source wagon: {source_wagon}\n"
                    f"  Target wagon: {target_wagon}\n"
                    f"  Import: {specifier}\n"
                    f"  Issue: Relative import escapes wagon boundary\n"
                    f"  Fix: Use barrel import '@/{target_wagon}/{{feature}}' instead"
                )

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} relative cross-wagon imports:\n\n"
            + "\n\n".join(violations[:10])
            + (f"\n\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
            + "\n\nRelative imports must not escape wagon boundaries."
            + "\nSee: atdd/coder/conventions/boundaries.convention.yaml"
        )


@pytest.mark.coder
def test_boundaries_convention_exists():
    """
    SPEC-BOUNDARIES-TS-0003: boundaries.convention.yaml exists.

    The boundaries convention file must exist and define the interaction
    section covering cross-wagon import rules.

    Given: ATDD coder conventions directory
    When: Checking for boundaries.convention.yaml
    Then: File exists with required sections
    """
    if not BOUNDARIES_CONVENTION.exists():
        pytest.fail(
            f"\n\nMissing convention file: {BOUNDARIES_CONVENTION}"
            + "\n\nCreate src/atdd/coder/conventions/boundaries.convention.yaml"
        )

    import yaml
    with open(BOUNDARIES_CONVENTION, "r", encoding="utf-8") as f:
        convention = yaml.safe_load(f)

    required_sections = ["namespacing", "interaction"]
    missing = [s for s in required_sections if s not in convention]

    if missing:
        pytest.fail(
            f"\n\nboundaries.convention.yaml missing required sections:\n\n"
            + "\n".join(f"  - {s}" for s in missing)
        )
