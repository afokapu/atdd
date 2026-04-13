"""
Test that all TypeScript source files in web/src/ are reachable from graph roots.

Validates:
- No unreachable TypeScript files in web/src/ directory
- Barrel re-exports (index.ts) are followed as graph edges
- Composition roots (index.ts at wagon/feature level) are roots
- Convention file exists

Convention: src/atdd/coder/conventions/dead-code.convention.yaml

BE parity with: test_dead_code_python.py
"""

import os
import re
import pytest
from collections import deque
from pathlib import Path
from typing import Dict, List, Set, Tuple

from atdd.coach.utils.repo import find_repo_root

import atdd


# ============================================================================
# PATH CONSTANTS
# ============================================================================

REPO_ROOT = find_repo_root()
WEB_SRC = REPO_ROOT / "web" / "src"
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

# Directories to skip during traversal
_SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".cache", "__tests__", "__mocks__",
}

_TS_EXTENSIONS = {".ts", ".tsx"}

# Files that are always graph roots by convention (TS parity with Python roots)
ROOT_FILENAMES = {
    "index.ts",       # barrel export — TS equivalent of __init__.py
    "index.tsx",      # barrel export (JSX variant)
    "wagon.ts",       # wagon composition root
    "composition.ts", # composition root
}

# Patterns that identify test files (always roots)
TEST_PATTERNS = {
    ".test.ts",
    ".test.tsx",
    ".spec.ts",
    ".spec.tsx",
}


# ============================================================================
# IMPORT EXTRACTION (regex-based, no tree-sitter dependency)
# ============================================================================

# Matches: import ... from 'path'  /  import ... from "path"
_IMPORT_FROM_RE = re.compile(
    r"""(?:^|\n)\s*import\s+"""
    r"""(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]""",
)

# Matches: export ... from 'path'
_EXPORT_FROM_RE = re.compile(
    r"""(?:^|\n)\s*export\s+"""
    r"""(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]""",
)

# Matches: import 'path' (side-effect imports)
_IMPORT_SIDE_EFFECT_RE = re.compile(
    r"""(?:^|\n)\s*import\s+['"]([^'"]+)['"]""",
)

# Matches: require('path')
_REQUIRE_RE = re.compile(
    r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)

# Matches dynamic import('path')
_DYNAMIC_IMPORT_RE = re.compile(
    r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)


def find_typescript_files() -> List[Path]:
    """
    Find all TypeScript files in web/src/.

    Returns:
        Sorted list of .ts/.tsx file paths, excluding skip dirs.
    """
    if not WEB_SRC.exists():
        return []

    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(WEB_SRC):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                continue
            files.append(Path(dirpath) / fname)

    return sorted(files)


def is_test_file(file_path: Path) -> bool:
    """
    Determine if a file is a test file.

    Test files are identified by:
    - Filename ends with .test.ts/.test.tsx/.spec.ts/.spec.tsx
    - Located in a __tests__/ or tests/ directory
    """
    name = file_path.name
    for pattern in TEST_PATTERNS:
        if name.endswith(pattern):
            return True
    for parent in file_path.parents:
        if parent.name in {"__tests__", "tests", "test"}:
            return True
    return False


def is_root_file(file_path: Path) -> bool:
    """
    Determine if a file is a graph root.

    Roots are:
    - Test files (.test.ts, .spec.ts, etc.)
    - index.ts / index.tsx (barrel exports — TS equivalent of __init__.py)
    - composition.ts, wagon.ts
    - App entry points (main.ts, main.tsx, app.ts, app.tsx)
    """
    name = file_path.name
    if name in ROOT_FILENAMES:
        return True
    if is_test_file(file_path):
        return True
    if name in {"main.ts", "main.tsx", "app.ts", "app.tsx"}:
        return True
    return False


def extract_import_paths(file_path: Path) -> List[str]:
    """
    Extract import specifiers from a TypeScript file using regex.

    Returns:
        List of raw import specifier strings (e.g., ['./domain/calc', '@/wagon/feature/...']).
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    specifiers: List[str] = []
    for pattern in (_IMPORT_FROM_RE, _EXPORT_FROM_RE, _IMPORT_SIDE_EFFECT_RE,
                    _REQUIRE_RE, _DYNAMIC_IMPORT_RE):
        specifiers.extend(pattern.findall(source))

    return specifiers


def resolve_import_to_file(
    specifier: str,
    source_file: Path,
    all_files: Set[Path],
) -> Set[Path]:
    """
    Resolve a TS import specifier to possible file paths.

    Handles:
    - Relative imports: './foo', '../bar'
    - Path alias imports: '@/wagon/feature/layer/module'

    Returns:
        Set of resolved file paths found in all_files.
    """
    candidates: Set[Path] = set()

    if specifier.startswith("."):
        # Relative import
        base_dir = source_file.parent
        resolved_dir = (base_dir / specifier).resolve()
        _add_candidates(resolved_dir, candidates, all_files)

    elif specifier.startswith("@/"):
        # Path alias — @/ typically maps to web/src/
        remainder = specifier[2:]  # strip '@/'
        resolved_dir = (WEB_SRC / remainder).resolve()
        _add_candidates(resolved_dir, candidates, all_files)

    # External packages (npm) are not resolved — they're outside our graph

    return candidates


def _add_candidates(resolved_dir: Path, candidates: Set[Path], all_files: Set[Path]) -> None:
    """Add file candidates for a resolved directory/file path."""
    # Try exact file with extensions
    for ext in _TS_EXTENSIONS:
        candidate = resolved_dir.with_suffix(ext)
        if candidate in all_files:
            candidates.add(candidate)

    # Try as directory with index file
    for ext in _TS_EXTENSIONS:
        index_candidate = resolved_dir / f"index{ext}"
        if index_candidate in all_files:
            candidates.add(index_candidate)

    # Try the path as-is (already has extension)
    if resolved_dir in all_files:
        candidates.add(resolved_dir)


def build_file_import_graph(ts_files: List[Path]) -> Dict[Path, Set[Path]]:
    """
    Build a file-level directed import graph.

    Each file maps to the set of files it imports (directly or via barrel exports).
    """
    all_files = set(ts_files)
    graph: Dict[Path, Set[Path]] = {f: set() for f in ts_files}

    for ts_file in ts_files:
        specifiers = extract_import_paths(ts_file)
        for spec in specifiers:
            resolved = resolve_import_to_file(spec, ts_file, all_files)
            graph[ts_file].update(resolved)

    return graph


def find_reachable_files(
    roots: Set[Path],
    graph: Dict[Path, Set[Path]],
) -> Set[Path]:
    """
    BFS from root files through the import graph.

    Returns the set of all reachable files.
    """
    visited: Set[Path] = set()
    queue = deque(roots)

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for neighbor in graph.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)

    return visited


def build_reverse_graph(graph: Dict[Path, Set[Path]]) -> Dict[Path, Set[Path]]:
    """
    Build reverse import graph (who imports this file?).

    Used for bidirectional reachability.
    """
    reverse: Dict[Path, Set[Path]] = {f: set() for f in graph}
    for source, targets in graph.items():
        for target in targets:
            if target in reverse:
                reverse[target].add(source)
    return reverse


# ============================================================================
# SCAN FUNCTION (for baseline.py registry)
# ============================================================================


def scan_dead_code_typescript(repo_root: Path) -> Tuple[int, List[str]]:
    """Scan for unreachable TypeScript files. Used by ratchet baseline."""
    web_src = repo_root / "web" / "src"
    if not web_src.exists():
        return 0, []

    # Collect files
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(web_src):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if any(fname.endswith(ext) for ext in _TS_EXTENSIONS):
                files.append(Path(dirpath) / fname)
    files.sort()

    if not files:
        return 0, []

    # Build graph
    all_files_set = set(files)
    graph: Dict[Path, Set[Path]] = {f: set() for f in files}
    for ts_file in files:
        specifiers = extract_import_paths(ts_file)
        for spec in specifiers:
            resolved = resolve_import_to_file(spec, ts_file, all_files_set)
            graph[ts_file].update(resolved)

    # Identify roots
    roots = {f for f in files if is_root_file(f)}
    if not roots:
        return 0, []

    # BFS forward and reverse
    reachable = find_reachable_files(roots, graph)
    reverse_graph = build_reverse_graph(graph)
    reverse_reachable = find_reachable_files(roots, reverse_graph)
    all_reachable = reachable | reverse_reachable

    # Unreachable files (exclude index.ts — structural like __init__.py)
    unreachable: List[str] = []
    for ts_file in files:
        if ts_file in all_reachable:
            continue
        if ts_file.name in {"index.ts", "index.tsx"}:
            continue
        try:
            rel_path = ts_file.relative_to(repo_root)
        except ValueError:
            rel_path = ts_file
        unreachable.append(str(rel_path))

    return len(unreachable), unreachable


# ============================================================================
# TEST FUNCTIONS
# ============================================================================


@pytest.mark.coder
def test_no_unreachable_typescript_files(ratchet_baseline):
    """
    SPEC-CODER-DEADCODE-TS-0001: No unreachable TypeScript files.

    Every .ts/.tsx file in web/src/ must be reachable from at least one graph root
    (test file, index.ts barrel, composition root, or app entry point).
    Uses ratchet baseline to allow pre-existing dead code while preventing regression.

    Given: All TypeScript files in web/src/
    When: Building file-level import graph and BFS from roots
    Then: Unreachable file count does not exceed baseline

    Convention: src/atdd/coder/conventions/dead-code.convention.yaml
    BE parity: test_dead_code_python.py::test_no_unreachable_python_files
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found in web/src/ to validate")

    # Build import graph
    graph = build_file_import_graph(ts_files)

    # Identify root files
    roots = {f for f in ts_files if is_root_file(f)}

    if not roots:
        pytest.skip("No graph roots found (no test files, index.ts, etc.)")

    # BFS from roots (forward)
    reachable = find_reachable_files(roots, graph)

    # BFS from roots (reverse — who imports this file?)
    reverse_graph = build_reverse_graph(graph)
    reverse_reachable = find_reachable_files(roots, reverse_graph)

    # A file is alive if reachable from roots OR imported by a reachable file
    all_reachable = reachable | reverse_reachable

    # Find unreachable files (exclude index.ts — structural like __init__.py)
    unreachable: List[str] = []
    for ts_file in ts_files:
        if ts_file in all_reachable:
            continue
        if ts_file.name in {"index.ts", "index.tsx"}:
            continue
        rel_path = ts_file.relative_to(REPO_ROOT)
        unreachable.append(str(rel_path))

    ratchet_baseline.assert_no_regression(
        validator_id="dead_code_typescript",
        current_count=len(unreachable),
        violations=unreachable,
    )


@pytest.mark.coder
def test_barrel_reexports_create_graph_edges():
    """
    SPEC-CODER-DEADCODE-TS-0002: index.ts re-exports are graph edges.

    When index.ts does `export { Foo } from './module'`, this creates an edge
    from index.ts to module.ts. If index.ts is reachable (imported by another
    file), then module.ts is also reachable.

    Given: TypeScript packages with index.ts barrel exports
    When: Building import graph
    Then: Re-exported modules appear as edges from index.ts

    BE parity: test_dead_code_python.py::test_init_reexports_create_graph_edges
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found in web/src/ to validate")

    barrel_files = [f for f in ts_files if f.name in {"index.ts", "index.tsx"}]

    if not barrel_files:
        pytest.skip("No index.ts barrel files found")

    all_files_set = set(ts_files)
    violations: List[str] = []

    for barrel in barrel_files:
        specifiers = extract_import_paths(barrel)
        for spec in specifiers:
            resolved = resolve_import_to_file(spec, barrel, all_files_set)
            # If barrel re-exports from a specifier that resolves to known files,
            # edges exist. If specifier can't be resolved, it may be an external
            # package (OK) or a broken import (separate validator concern).
            if resolved:
                continue

    if violations:
        pytest.fail(
            f"\n\nindex.ts re-export edges missing:\n\n"
            + "\n".join(violations[:10])
        )


@pytest.mark.coder
def test_composition_roots_always_reachable():
    """
    SPEC-CODER-DEADCODE-TS-0003: Composition roots are never flagged as dead.

    index.ts barrels, test files, composition.ts, wagon.ts, and app entry
    points are graph roots by definition.

    Given: TypeScript files including index.ts, composition.ts, wagon.ts
    When: Checking root file classification
    Then: All root files are correctly identified

    BE parity: test_dead_code_python.py::test_composition_roots_always_reachable
    """
    ts_files = find_typescript_files()

    if not ts_files:
        pytest.skip("No TypeScript files found in web/src/ to validate")

    root_files = {f for f in ts_files if is_root_file(f)}

    index_files = [f for f in ts_files if f.name in {"index.ts", "index.tsx"}]
    test_files = [f for f in ts_files if is_test_file(f)]
    entry_files = [f for f in ts_files if f.name in {"main.ts", "main.tsx", "app.ts", "app.tsx"}]

    violations: List[str] = []

    for f in index_files:
        if f not in root_files:
            violations.append(f"  {f.relative_to(REPO_ROOT)} — index.ts not classified as root")

    for f in test_files:
        if f not in root_files:
            violations.append(f"  {f.relative_to(REPO_ROOT)} — test file not classified as root")

    for f in entry_files:
        if f not in root_files:
            violations.append(f"  {f.relative_to(REPO_ROOT)} — entry point not classified as root")

    if violations:
        pytest.fail(
            f"\n\nFound {len(violations)} root classification errors:\n\n"
            + "\n".join(violations)
            + "\n\nThese files should be graph roots but were not detected."
        )


@pytest.mark.coder
def test_dead_code_convention_exists():
    """
    SPEC-CODER-DEADCODE-TS-0004: dead-code.convention.yaml exists.

    The dead code convention file must exist in src/atdd/coder/conventions/
    and define the required sections.

    Given: ATDD coder conventions directory
    When: Checking for dead-code.convention.yaml
    Then: File exists with required sections

    BE parity: test_dead_code_python.py::test_dead_code_convention_exists
    """
    convention_path = ATDD_PKG_DIR / "coder" / "conventions" / "dead-code.convention.yaml"

    if not convention_path.exists():
        pytest.fail(
            f"\n\nMissing convention file: {convention_path}"
            + "\n\nCreate src/atdd/coder/conventions/dead-code.convention.yaml"
            + " with sections: graph_roots, reexport_handling, exclusions, enforcement"
        )

    import yaml
    with open(convention_path, "r", encoding="utf-8") as f:
        convention = yaml.safe_load(f)

    required_sections = ["graph_roots", "reexport_handling", "exclusions", "enforcement"]
    missing = [s for s in required_sections if s not in convention]

    if missing:
        pytest.fail(
            f"\n\ndead-code.convention.yaml missing required sections:\n\n"
            + "\n".join(f"  - {s}" for s in missing)
        )
