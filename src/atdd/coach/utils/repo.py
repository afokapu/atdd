"""
Repository root detection utility.

Finds the consumer repository root using multiple detection strategies:
1. ATDD_REPO_ROOT env var (set by test runner for validators)
2. .atdd/manifest.yaml (preferred - explicit ATDD project marker)
3. plan/ AND contracts/ both exist (ATDD project structure)
4. .git/ directory (fallback - any git repo)
5. cwd (last resort - allows commands to work on uninitialized repos)

This ensures ATDD commands operate on the user's repo, not the package root.

For validators running from the installed package, the test runner sets
ATDD_REPO_ROOT to point to the consumer repo being validated.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Find repo root by searching upward for ATDD project markers.

    Detection order (first match wins):
    1. ATDD_REPO_ROOT env var - set by test runner for validators
    2. .atdd/manifest.yaml - explicit ATDD project marker
    3. plan/ AND contracts/ both exist - ATDD project structure
    4. .git/ directory - fallback for any git repository
    5. cwd - last resort if no markers found

    Args:
        start: Starting directory (default: cwd)

    Returns:
        Path to repo root (falls back to cwd if no markers found)

    Note:
        Results are cached for performance. If .atdd/manifest.yaml is not found,
        commands may operate in a degraded mode.

        For validators running from installed package, ATDD_REPO_ROOT env var
        is set by the test runner to point to the consumer repo.
    """
    # Strategy 0: Check ATDD_REPO_ROOT env var (set by test runner)
    env_root = os.environ.get("ATDD_REPO_ROOT")
    if env_root:
        env_path = Path(env_root).resolve()
        if env_path.is_dir():
            return env_path

    current = start or Path.cwd()
    current = current.resolve()

    while current != current.parent:
        # Strategy 1: .atdd/manifest.yaml (preferred)
        if (current / ".atdd" / "manifest.yaml").is_file():
            return current

        # Strategy 2: plan/ AND contracts/ both exist
        if (current / "plan").is_dir() and (current / "contracts").is_dir():
            return current

        # Strategy 3: .git/ directory (fallback)
        if (current / ".git").is_dir():
            return current

        current = current.parent

    # Strategy 4: Return starting directory as last resort
    # Commands can handle uninitialized repos appropriately
    return start.resolve() if start else Path.cwd().resolve()


@lru_cache(maxsize=1)
def is_consumer_project(start: Optional[Path] = None) -> bool:
    """
    Detect whether the current repo is a consumer project (not the atdd package itself).

    Detection: checks pyproject.toml for name = "atdd" (definitive),
    falls back to checking if src/atdd/planner/validators/ exists.

    Returns:
        True if this is a consumer project, False if this is the atdd package repo.
    """
    root = find_repo_root(start)

    # Definitive check: pyproject.toml with name = "atdd"
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("name") and "=" in stripped:
                    value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    if value == "atdd":
                        return False
        except OSError:
            pass

    # Fallback: if src/atdd/planner/validators/ exists, it's the atdd package
    if (root / "src" / "atdd" / "planner" / "validators").is_dir():
        return False

    return True


def detect_worktree_layout(start: Optional[Path] = None) -> str:
    """
    Detect the worktree layout of a repository.

    Returns:
        "worktree-ready" - .git is a dir and parent dir is named "main"
        "worktree"       - .git is a file (linked worktree)
        "flat"           - .git is a dir but parent dir is not "main"
        "no-git"         - no .git found
    """
    root = start or Path.cwd()
    root = root.resolve()

    git_path = root / ".git"

    if git_path.is_file():
        return "worktree"

    if git_path.is_dir():
        if root.name == "main":
            return "worktree-ready"
        return "flat"

    return "no-git"


def require_repo_root(start: Optional[Path] = None) -> Path:
    """
    Find repo root, raising RuntimeError if no markers found.

    This is a stricter version of find_repo_root() for commands that
    require a valid ATDD project structure.

    Args:
        start: Starting directory (default: cwd)

    Returns:
        Path to repo root

    Raises:
        RuntimeError: If no ATDD project markers (.atdd/manifest.yaml,
                     plan/ + contracts/, or .git/) are found
    """
    current = start or Path.cwd()
    current = current.resolve()
    start_path = current

    while current != current.parent:
        # Check for any valid marker
        if (current / ".atdd" / "manifest.yaml").is_file():
            return current
        if (current / "plan").is_dir() and (current / "contracts").is_dir():
            return current
        if (current / ".git").is_dir():
            return current

        current = current.parent

    raise RuntimeError(
        f"No ATDD project markers found searching from {start_path}. "
        "Expected one of: .atdd/manifest.yaml, plan/ + contracts/, or .git/"
    )
