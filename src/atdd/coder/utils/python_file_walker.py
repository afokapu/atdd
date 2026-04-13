"""
Shared walker that yields Python source files belonging to the *consumer*
repository under scan, excluding vendored/virtualenv/build artifacts.

Why this exists
---------------
Historically, individual coder validators reimplemented their own
``rglob("*.py")`` walk plus an ad-hoc skip list. When ``atdd`` is
pip-installed into a consumer repo and the validators receive a path that
incidentally contains ``site-packages`` or ``.venv``, those ad-hoc walks
leaked into vendored code and produced spurious violations against third
party libraries (issue #272).

This module centralises a single walker with a canonical exclude list so
every validator sees the same "what counts as consumer code" universe.

Strategy
--------
1. Try ``git ls-files -- "*.py"`` with ``cwd=root``. If ``root`` is inside a
   git working tree, this returns only tracked files — vendored code in
   ``.venv`` / ``site-packages`` is typically untracked and therefore
   naturally excluded.
2. Fallback to ``Path.rglob("*.py")`` with :data:`DEFAULT_EXCLUDE_PATTERNS`
   applied to path parts (for non-git directories, fresh clones before
   ``git add``, or git checkouts where .venv is tracked by mistake).

The exclude filter is applied in **both** strategies as a belt-and-braces
guard, so a stray tracked ``.venv`` cannot reintroduce the site-packages
leak.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import FrozenSet, Iterator, List, Optional, Tuple


# Directory-name components that indicate a vendored / virtualenv / build
# artifact location. Any path whose relative parts (relative to the walker
# root) include one of these is skipped unconditionally.
#
# Kept deliberately minimal and conservative: this list covers the common
# offenders across Python ecosystems. It is NOT intended as a replacement
# for project-specific excludes — validators that need finer control should
# filter the walker's output.
DEFAULT_EXCLUDE_PATTERNS: FrozenSet[str] = frozenset(
    {
        # Python virtualenvs / package managers
        "site-packages",
        ".venv",
        "venv",
        "env",
        "envs",
        ".tox",
        "__pypackages__",
        ".eggs",
        # JS (in case a python walker is pointed at a polyglot tree)
        "node_modules",
        # Build/dist output
        "build",
        "dist",
        # Python caches
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        # Version control
        ".git",
        ".hg",
        ".svn",
    }
)


def _is_excluded_relative(rel_parts: Tuple[str, ...]) -> bool:
    """Return True if any component of the relative path is vendored."""
    for part in rel_parts:
        if part in DEFAULT_EXCLUDE_PATTERNS:
            return True
        # *.dist-info / *.egg-info directories (pip metadata)
        if part.endswith(".dist-info") or part.endswith(".egg-info"):
            return True
        # conda env roots (best-effort)
        if part in {"miniconda3", "anaconda3", "miniforge3"}:
            return True
    return False


def _git_ls_files(root: Path) -> Optional[List[Path]]:
    """
    Try ``git ls-files -- '*.py'`` with cwd=root. Returns a list of absolute
    Paths, or None if the call failed (root not in a git tree, git missing,
    non-zero exit).
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", "*.py"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    paths: List[Path] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        candidate = (root / line).resolve()
        if candidate.is_file():
            paths.append(candidate)
    return paths


def _rglob_files(root: Path) -> List[Path]:
    """Fallback walker — plain Path.rglob, caller filters excludes."""
    return [p for p in root.rglob("*.py") if p.is_file()]


def walk_consumer_python_files(repo_root: Path) -> Iterator[Path]:
    """
    Yield absolute :class:`pathlib.Path` objects for every Python source
    file under ``repo_root`` that belongs to the consumer project (not
    vendored/virtualenv/build output).

    Parameters
    ----------
    repo_root:
        Directory to walk. May be the repository root itself or any
        subdirectory (e.g. ``repo_root / "python"``). A non-existent
        directory yields nothing.

    Yields
    ------
    Path
        Absolute path to a ``.py`` file whose relative location under
        ``repo_root`` does not contain any :data:`DEFAULT_EXCLUDE_PATTERNS`
        component.
    """
    if not repo_root.exists():
        return
    resolved_root = repo_root.resolve()

    files = _git_ls_files(resolved_root)
    if files is None:
        files = _rglob_files(resolved_root)

    for path in files:
        try:
            rel_parts = path.resolve().relative_to(resolved_root).parts
        except ValueError:
            # git ls-files can surface paths outside root via symlinks;
            # skip anything we cannot express relative to the walk root.
            continue
        if _is_excluded_relative(rel_parts):
            continue
        yield path
