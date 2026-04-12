"""
Test that hook files exceeding a size threshold are allowlisted.

Validates:
- SPEC-CODER-PAGE-0003: Hooks exceeding max_lines not in allowlist are a hard failure

God hooks (200+ lines) doing cross-wagon state coordination should be
decomposed into smaller single-concern hooks or promoted to train-level
artifacts.

Convention: src/atdd/coder/conventions/frontend.convention.yaml → train_composition
Config: .atdd/config.yaml → god_hook_elimination
"""

import fnmatch
import os
import yaml
import pytest
from pathlib import Path
from typing import Dict, List, Tuple

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
REPO_ROOT = find_repo_root()

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".dart_tool",
    "build", ".pub-cache", "dist", ".next", ".nuxt", "coverage",
    ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache",
}

_TS_EXTENSIONS = (".ts", ".tsx")

_DEFAULT_MAX_LINES = 200
_DEFAULT_HOOK_PATTERNS = ["use*.ts", "use*.tsx"]
_DEFAULT_SCAN_DIR = "web/src"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def _load_god_hook_config() -> Dict:
    """Load god_hook_elimination config from .atdd/config.yaml."""
    config = load_atdd_config(REPO_ROOT)
    return config.get("god_hook_elimination", {})


def _load_allowlist(gh_config: Dict) -> Dict[str, Dict]:
    """
    Build path→entry map from allowlist.

    Returns:
        Dict mapping relative file paths to their full allowlist entry
        (includes lines, migration fields).
    """
    allowlist = {}
    for entry in gh_config.get("allowlist", []):
        path = entry.get("path", "")
        if path:
            allowlist[path] = entry
    return allowlist


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def _find_hook_files(
    scan_dir: str,
    hook_patterns: List[str],
) -> List[Path]:
    """Find all files matching hook_patterns under scan_dir."""
    base = REPO_ROOT / scan_dir
    if not base.exists():
        return []

    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(tuple(_TS_EXTENSIONS)):
                continue
            # Check against hook patterns
            for pattern in hook_patterns:
                if fnmatch.fnmatch(fname, pattern):
                    files.append(Path(dirpath) / fname)
                    break
    return sorted(files)


def _count_lines(file_path: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------
@pytest.mark.coder
def test_god_hooks_must_be_allowlisted():
    """
    SPEC-CODER-PAGE-0003: Hook files exceeding max_lines not in allowlist fail.

    Large hooks (200+ lines) doing cross-wagon state coordination should be
    decomposed or promoted to train-level artifacts. Each allowlisted hook
    must reference a migration issue.

    Given: Hook files matching hook_patterns in scan directory
    When: Checking line count against max_lines threshold
    Then: Hooks exceeding threshold without allowlist entry are hard failures
    """
    gh_config = _load_god_hook_config()

    if not gh_config:
        pytest.skip(
            "No god_hook_elimination configured in .atdd/config.yaml — "
            "consumer repo must define hook elimination rules"
        )

    max_lines = gh_config.get("max_lines", _DEFAULT_MAX_LINES)
    hook_patterns = gh_config.get("hook_patterns", _DEFAULT_HOOK_PATTERNS)
    scan_dir = gh_config.get("scan_dir", _DEFAULT_SCAN_DIR)
    allowlist = _load_allowlist(gh_config)

    hook_files = _find_hook_files(scan_dir, hook_patterns)

    if not hook_files:
        pytest.skip("No hook files found matching hook_patterns")

    violations: List[str] = []

    for file_path in hook_files:
        line_count = _count_lines(file_path)

        if line_count <= max_lines:
            continue

        rel_path = str(file_path.relative_to(REPO_ROOT))

        if rel_path in allowlist:
            entry = allowlist[rel_path]
            migration = entry.get("migration", "")
            if not migration or not migration.strip():
                violations.append(
                    f"  SPEC-CODER-PAGE-0003 FAIL: Allowlisted god hook missing migration reference\n"
                    f"    File:   {rel_path}\n"
                    f"    Lines:  {line_count} (threshold: {max_lines})\n"
                    f"    Fix:    Add migration: \"owner/repo#NNN\" to the allowlist entry."
                )
            continue

        violations.append(
            f"  SPEC-CODER-PAGE-0003 FAIL: God hook exceeds {max_lines}-line threshold\n"
            f"    File:   {rel_path}\n"
            f"    Lines:  {line_count} (threshold: {max_lines})\n"
            f"    Fix:    Decompose into smaller single-concern hooks,\n"
            f"            or add to god_hook_elimination.allowlist in .atdd/config.yaml\n"
            f"            with a migration issue reference.\n"
            f"            See: frontend.convention.yaml → train_composition"
        )

    if violations:
        pytest.fail(
            f"\n\n{len(violations)} god hook violation(s):\n\n"
            + "\n\n".join(violations)
        )


@pytest.mark.coder
def test_god_hook_allowlist_entries_have_migration():
    """
    SPEC-CODER-PAGE-0003 (allowlist hygiene): Every god hook allowlist entry
    must reference a migration issue and declare its current line count.

    Given: god_hook_elimination.allowlist in .atdd/config.yaml
    When: Checking each entry for required fields
    Then: Entries missing migration or lines field fail
    """
    gh_config = _load_god_hook_config()
    allowlist_entries = gh_config.get("allowlist", [])

    if not allowlist_entries:
        pytest.skip("No god_hook_elimination.allowlist entries in .atdd/config.yaml")

    violations: List[str] = []

    for entry in allowlist_entries:
        path = entry.get("path", "<missing path>")
        migration = entry.get("migration", "")
        lines = entry.get("lines")

        missing_fields = []
        if not migration or not migration.strip():
            missing_fields.append("migration")
        if lines is None:
            missing_fields.append("lines")

        if missing_fields:
            violations.append(
                f"  SPEC-CODER-PAGE-0003 FAIL: Allowlist entry missing required field(s)\n"
                f"    Path:    {path}\n"
                f"    Missing: {', '.join(missing_fields)}\n"
                f"    Fix:     Add {' and '.join(missing_fields)} to the allowlist entry."
            )

    if violations:
        pytest.fail(
            f"\n\n{len(violations)} god hook allowlist entry/entries with missing fields:\n\n"
            + "\n\n".join(violations)
        )
