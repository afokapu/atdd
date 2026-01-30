"""
Repository root detection utility.

Finds the consumer repository root by searching upward for .atdd/ directory.
This ensures ATDD commands operate on the user's repo, not the package root.
"""

from pathlib import Path


def find_repo_root(start: Path = None) -> Path:
    """
    Find repo root by searching upward for .atdd/ directory.

    Args:
        start: Starting directory (default: cwd)

    Returns:
        Path to repo root (directory containing .atdd/)

    Note:
        If .atdd/ is not found, returns the starting directory (cwd).
        This allows commands to work on non-initialized repos,
        though they may operate in a degraded mode.
    """
    current = start or Path.cwd()
    current = current.resolve()

    while current != current.parent:
        if (current / ".atdd").is_dir():
            return current
        current = current.parent

    # Not found - return starting directory
    # Commands can handle uninitialized repos appropriately
    return start.resolve() if start else Path.cwd().resolve()
