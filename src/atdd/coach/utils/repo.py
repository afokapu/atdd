"""
Repository root detection utility.

Finds the consumer repository root using multiple detection strategies:
1. .atdd/manifest.yaml (preferred - explicit ATDD project marker)
2. plan/ AND contracts/ both exist (ATDD project structure)
3. .git/ directory (fallback - any git repo)
4. cwd (last resort - allows commands to work on uninitialized repos)

This ensures ATDD commands operate on the user's repo, not the package root.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Find repo root by searching upward for ATDD project markers.

    Detection order (first match wins):
    1. .atdd/manifest.yaml - explicit ATDD project marker
    2. plan/ AND contracts/ both exist - ATDD project structure
    3. .git/ directory - fallback for any git repository
    4. cwd - last resort if no markers found

    Args:
        start: Starting directory (default: cwd)

    Returns:
        Path to repo root (falls back to cwd if no markers found)

    Note:
        Results are cached for performance. If .atdd/manifest.yaml is not found,
        commands may operate in a degraded mode.
    """
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
