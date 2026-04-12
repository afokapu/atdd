"""
Test that all files in page directories are either allowlisted or permanent exceptions.

Validates:
- SPEC-CODER-PAGE-0001: Files in scan_dirs not in allowlist and not permanent exceptions fail
- SPEC-CODER-PAGE-0002: Allowlist entries must reference a migration issue
- SPEC-CODER-PAGE-0005: Pages with zero wagon imports are auto-detected permanent exceptions
- SPEC-CODER-PAGE-0010: Subdirectories under pages/ are a hard failure
- SPEC-CODER-PAGE-0011: Full pages/ tree scan — any file in pages/ not in allowlist fails

Convention: src/atdd/coder/conventions/frontend.convention.yaml → train_composition
Config: .atdd/config.yaml → page_elimination
"""

import os
import re
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Set, Tuple

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()
CONFIG_PATH = REPO_ROOT / ".atdd" / "config.yaml"

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}

_TS_EXTENSIONS = (".ts", ".tsx")

# Regex to detect wagon-level imports.
# Matches: import ... from '../../<wagon>/' or '../<wagon>/' or '@<wagon>/'
# Also matches: from '<wagon>/' style imports that reference known wagon paths.
_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+|import\s*\()\s*['"]([^'"]+)['"]"""
)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def _load_page_elimination_config() -> Dict:
    """Load page_elimination config from .atdd/config.yaml."""
    config = load_atdd_config(REPO_ROOT)
    return config.get("page_elimination", {})


def _load_allowlist(pe_config: Dict) -> Dict[str, str]:
    """
    Build path→migration map from allowlist entries.

    Returns:
        Dict mapping relative file paths to migration issue references.
    """
    allowlist = {}
    for entry in pe_config.get("allowlist", []):
        path = entry.get("path", "")
        migration = entry.get("migration", "")
        if path:
            allowlist[path] = migration
    return allowlist


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def _find_all_files_in_scan_dirs(scan_dirs: List[str]) -> List[Path]:
    """Walk scan_dirs and collect all files (not just *Page.tsx)."""
    files: List[Path] = []
    for scan_dir in scan_dirs:
        base = REPO_ROOT / scan_dir
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if fname.endswith(tuple(_TS_EXTENSIONS)):
                    files.append(Path(dirpath) / fname)
    return sorted(files)


def _find_subdirectories_in_scan_dirs(scan_dirs: List[str]) -> List[Path]:
    """Find subdirectories directly under scan_dirs (pages/ should be flat)."""
    subdirs: List[Path] = []
    for scan_dir in scan_dirs:
        base = REPO_ROOT / scan_dir
        if not base.exists():
            continue
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and entry.name not in _SKIP_DIRS:
                subdirs.append(entry)
    return subdirs


# ---------------------------------------------------------------------------
# Import analysis for permanent exception detection
# ---------------------------------------------------------------------------
def _extract_imports(file_path: Path) -> List[str]:
    """Extract import paths from a TypeScript file."""
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except (OSError, UnicodeDecodeError):
        return []

    return _IMPORT_RE.findall(content)


def _detect_wagon_dirs(scan_dirs: List[str]) -> Set[str]:
    """
    Detect wagon directory names by looking at the src path pattern.

    Wagons are top-level directories under web/src/ that contain
    domain/application/integration/presentation sub-layers.
    """
    web_src = REPO_ROOT / "web" / "src"
    if not web_src.exists():
        return set()

    wagon_dirs: Set[str] = set()
    layer_names = {"domain", "application", "integration", "presentation"}

    for entry in web_src.iterdir():
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in _SKIP_DIRS:
            continue
        # A directory is a wagon if it contains at least one layer subdirectory
        child_names = {c.name for c in entry.iterdir() if c.is_dir()}
        if child_names & layer_names:
            wagon_dirs.add(entry.name)

    return wagon_dirs


def _has_wagon_imports(file_path: Path, wagon_dirs: Set[str]) -> bool:
    """
    Check if a file imports from any wagon directory.

    A file with zero wagon imports is a permanent exception — it has nothing
    to compose into a train.
    """
    imports = _extract_imports(file_path)
    for imp in imports:
        # Check for relative imports that traverse into wagon directories
        segments = imp.replace("\\", "/").split("/")
        for seg in segments:
            if seg in wagon_dirs:
                return True
        # Check for alias imports like @wagon-name/
        for wagon in wagon_dirs:
            if imp.startswith(f"@{wagon}/") or imp.startswith(f"{wagon}/"):
                return True
    return False


def _has_application_hooks(file_path: Path) -> bool:
    """
    Check if a file imports application-layer hooks (use* from application/).

    Files using application hooks are not permanent exceptions — they
    orchestrate wagon logic and should be train compositions.
    """
    imports = _extract_imports(file_path)
    for imp in imports:
        if "/application/" in imp and "/hook" in imp.lower():
            return True
        if "/application/" in imp and "use" in imp.lower():
            return True
    return False


def _is_permanent_exception(file_path: Path, wagon_dirs: Set[str]) -> bool:
    """
    Auto-detect permanent exceptions: pages with zero wagon imports
    and zero application hooks.

    These pages have nothing to compose into a train.
    """
    return not _has_wagon_imports(file_path, wagon_dirs) and not _has_application_hooks(file_path)


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------
@pytest.mark.coder
def test_page_files_must_be_allowlisted_or_permanent_exceptions():
    """
    SPEC-CODER-PAGE-0001 + SPEC-CODER-PAGE-0005 + SPEC-CODER-PAGE-0011:
    Every file in scan_dirs must be in the allowlist or be an auto-detected
    permanent exception (zero wagon imports and zero application hooks).

    Given: All TS/TSX files in configured scan_dirs
    When: Checking each file against allowlist and import graph
    Then: Unlisted files with wagon dependencies are hard failures
    """
    pe_config = _load_page_elimination_config()
    scan_dirs = pe_config.get("scan_dirs", [])

    if not scan_dirs:
        pytest.skip(
            "No page_elimination.scan_dirs configured in .atdd/config.yaml — "
            "consumer repo must define scan directories"
        )

    files = _find_all_files_in_scan_dirs(scan_dirs)
    if not files:
        pytest.skip("No TypeScript files found in scan_dirs")

    allowlist = _load_allowlist(pe_config)
    wagon_dirs = _detect_wagon_dirs(scan_dirs)

    violations: List[str] = []
    permanent_exceptions: List[str] = []

    for file_path in files:
        rel_path = str(file_path.relative_to(REPO_ROOT))

        # Check allowlist
        if rel_path in allowlist:
            continue

        # Check permanent exception (auto-detected)
        if _is_permanent_exception(file_path, wagon_dirs):
            permanent_exceptions.append(rel_path)
            continue

        violations.append(
            f"  SPEC-CODER-PAGE-0001 FAIL: Unlisted page file\n"
            f"    File: {rel_path}\n"
            f"    Fix:  Route to a train instead. "
            f"See: frontend.convention.yaml → train_composition\n"
            f"          Create a TrainView component, not a Page component.\n"
            f"          Or add to page_elimination.allowlist in .atdd/config.yaml "
            f"with a migration issue."
        )

    if violations:
        header = (
            f"\n\n{len(violations)} unlisted page file(s) found.\n"
            f"{len(permanent_exceptions)} auto-detected permanent exception(s) (zero wagon imports).\n\n"
        )
        pytest.fail(header + "\n\n".join(violations))


@pytest.mark.coder
def test_allowlist_entries_have_migration_references():
    """
    SPEC-CODER-PAGE-0002: Every allowlist entry must reference a migration issue.

    The migration field creates accountability — each page has a named exit path.

    Given: page_elimination.allowlist in .atdd/config.yaml
    When: Checking each entry for migration field
    Then: Entries without migration references fail
    """
    pe_config = _load_page_elimination_config()
    allowlist_entries = pe_config.get("allowlist", [])

    if not allowlist_entries:
        pytest.skip("No page_elimination.allowlist entries in .atdd/config.yaml")

    violations: List[str] = []

    for entry in allowlist_entries:
        path = entry.get("path", "<missing path>")
        migration = entry.get("migration", "")

        if not migration or not migration.strip():
            violations.append(
                f"  SPEC-CODER-PAGE-0002 FAIL: Allowlist entry missing migration reference\n"
                f"    Path: {path}\n"
                f"    Fix:  Add migration: \"owner/repo#NNN\" referencing the issue "
                f"that will eliminate this page."
            )

    if violations:
        pytest.fail(
            f"\n\n{len(violations)} allowlist entry/entries missing migration reference:\n\n"
            + "\n\n".join(violations)
        )


@pytest.mark.coder
def test_no_subdirectories_in_page_dirs():
    """
    SPEC-CODER-PAGE-0010: Subdirectories under pages/ are a hard failure.

    A page needing a subdirectory is a wagon in disguise. It should be
    extracted into a proper wagon with its own layer structure.

    Given: scan_dirs with no_subdirectories: true
    When: Scanning for subdirectories
    Then: Any subdirectory is a hard failure
    """
    pe_config = _load_page_elimination_config()
    scan_dirs = pe_config.get("scan_dirs", [])
    no_subdirectories = pe_config.get("no_subdirectories", True)

    if not scan_dirs:
        pytest.skip("No page_elimination.scan_dirs configured in .atdd/config.yaml")

    if not no_subdirectories:
        pytest.skip("no_subdirectories is disabled in page_elimination config")

    subdirs = _find_subdirectories_in_scan_dirs(scan_dirs)

    if subdirs:
        violations = []
        for subdir in subdirs:
            rel = subdir.relative_to(REPO_ROOT)
            violations.append(
                f"  SPEC-CODER-PAGE-0010 FAIL: Subdirectory in pages/\n"
                f"    Dir:  {rel}\n"
                f"    Fix:  Extract into a wagon. A page needing a subdirectory "
                f"is a wagon in disguise.\n"
                f"          See: frontend.convention.yaml → train_composition"
            )

        pytest.fail(
            f"\n\n{len(violations)} subdirectory/subdirectories found in page scan_dirs:\n\n"
            + "\n\n".join(violations)
        )
