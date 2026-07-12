"""
Repository root detection utility.

Finds the consumer repository root using multiple detection strategies:
1. ATDD_REPO_ROOT env var (set by test runner for validators)
2. .atdd/config.yaml (preferred - explicit ATDD project marker)
3. plan/ AND contracts/ both exist (ATDD project structure)
4. .git/ directory (fallback - any git repo)
5. cwd (last resort - allows commands to work on uninitialized repos)

This ensures ATDD commands operate on the user's repo, not the package root.

For validators running from the installed package, the test runner sets
ATDD_REPO_ROOT to point to the consumer repo being validated.
"""

import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Find repo root by searching upward for ATDD project markers.

    Detection order (first match wins):
    1. ATDD_REPO_ROOT env var - set by test runner for validators
    2. .atdd/config.yaml - explicit ATDD project marker
    3. plan/ AND contracts/ both exist - ATDD project structure
    4. .git/ directory - fallback for any git repository
    5. cwd - last resort if no markers found

    Args:
        start: Starting directory (default: cwd)

    Returns:
        Path to repo root (falls back to cwd if no markers found)

    Note:
        Results are cached for performance. If .atdd/config.yaml is not found,
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
        # Strategy 1: .atdd/config.yaml (preferred — explicit ATDD marker)
        if (current / ".atdd" / "config.yaml").is_file():
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


def find_python_dir(repo_root: Optional[Path] = None) -> Path:
    """
    Find the Python source directory in a repo.

    Consumer repos use python/, the toolkit uses src/.
    Returns the first that exists, or python/ as default.
    """
    root = repo_root or find_repo_root()
    python_dir = root / "python"
    if python_dir.exists():
        return python_dir
    src_dir = root / "src"
    if src_dir.exists():
        return src_dir
    return python_dir  # default for consumer repos (may not exist yet)


def _git_common_dir(root: Path) -> Optional[Path]:
    """Return the absolute git common dir for a linked worktree, or None.

    For a linked worktree ``.git`` is a gitfile; the common dir is the shared
    ``.git`` of the primary checkout. Resolving it lets the layout detector
    tell whether the worktree belongs to a flat-sibling (``main/``) layout.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    common = Path(raw)
    if not common.is_absolute():
        common = root / common
    return common.resolve()


def detect_worktree_layout(start: Optional[Path] = None) -> str:
    """
    Detect the worktree layout of a repository.

    Returns:
        "worktree-ready" - a flat-sibling layout: either the primary checkout
                           directory is named "main", or a linked worktree
                           whose git common dir lives under a "main/" checkout
        "worktree"       - .git is a file (linked worktree) not under "main/"
        "flat"           - .git is a dir but parent dir is not "main"
        "no-git"         - no .git found
    """
    root = start or Path.cwd()
    root = root.resolve()

    git_path = root / ".git"

    if git_path.is_file():
        # A linked worktree. It belongs to a worktree-ready flat-sibling
        # layout when its common git dir sits inside a "main/" primary
        # checkout — that repo is already migrated, no re-migration needed.
        common = _git_common_dir(root)
        if common is not None and common.parent.name == "main":
            return "worktree-ready"
        return "worktree"

    if git_path.is_dir():
        if root.name == "main":
            return "worktree-ready"
        return "flat"

    return "no-git"


def _read_core_bare(root: Path) -> Optional[str]:
    """Return the effective ``core.bare`` value for *root*, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "core.bare"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def ensure_repo_not_falsely_bare(root: Optional[Path] = None) -> bool:
    """Self-heal a working-tree checkout falsely marked ``core.bare=true`` (#917).

    A normal checkout (``.git`` is a directory) and a linked worktree
    (``.git`` is a *file*) both ALWAYS have a working tree and must carry
    ``core.bare=false``. ``core.bare`` is a *shared/common* config key, so a
    single stray unscoped ``git config core.bare true`` — from a SMOKE test
    run in the wrong cwd, a crashed/killed run, or an xdist worker — bleeds
    into the common ``.git/config`` and every linked worktree then reads
    ``core.bare=true``. The next ``git add -A`` treats the checkout as bare
    (no working tree) and stages the entire tree as deleted: the #629/#917
    phantom-mass-deletion incident (Wave 12 shipped 220k-line deletions this
    way; this session nearly shipped 323k-line deletions twice).

    This guard runs at ATDD command entry: if it finds a working-tree
    checkout reporting ``core.bare=true``, it resets it to ``false`` BEFORE
    any later git operation can act on the poisoned value. Preventive and
    harness-agnostic — unlike the test-only conftest guards, it protects the
    production ``atdd`` flows (validate / pr / issue / coach).

    Args:
        root: checkout to inspect (defaults to cwd).

    Returns:
        True if it healed a contaminated config; False otherwise (no ``.git``,
        legitimately not bare, or git unavailable). Never raises.
    """
    import logging

    try:
        root = (root or Path.cwd()).resolve()
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return False

    git_path = root / ".git"
    # A bare repo has no ``.git`` entry (it IS the git dir). If ``.git`` exists
    # as a file or directory, this is a working-tree checkout that must never
    # be bare. If it is absent, there is nothing here for us to protect.
    if not git_path.exists():
        return False

    if _read_core_bare(root) != "true":
        return False

    # Working-tree checkout reporting bare=true → contamination. Reset it.
    # ``core.bare`` is not worktree-scoped, so this writes the shared
    # ``.git/config`` and heals every linked worktree at once.
    try:
        result = subprocess.run(
            ["git", "config", "core.bare", "false"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return False
    if result.returncode != 0:
        return False

    logging.getLogger(__name__).warning(
        "atdd: healed core.bare=true on working-tree checkout %s — reset to "
        "false to prevent phantom mass-deletion (#917).",
        root,
        extra={"root": str(root), "guard": "core-bare-self-heal", "issue": 917},
    )
    return True


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
        RuntimeError: If no ATDD project markers (.atdd/config.yaml,
                     plan/ + contracts/, or .git/) are found
    """
    current = start or Path.cwd()
    current = current.resolve()
    start_path = current

    while current != current.parent:
        # Check for any valid marker
        if (current / ".atdd" / "config.yaml").is_file():
            return current
        if (current / "plan").is_dir() and (current / "contracts").is_dir():
            return current
        if (current / ".git").is_dir():
            return current

        current = current.parent

    raise RuntimeError(
        f"No ATDD project markers found searching from {start_path}. "
        "Expected one of: .atdd/config.yaml, plan/ + contracts/, or .git/"
    )


# Path parts that indicate a pip-installed / vendored location. Even if the
# consumer's `.venv` sits inside their repo root, `atdd.__file__` under any of
# these is a consumer install, NOT the atdd source repo.
_VENDORED_PATH_MARKERS = frozenset(
    {
        "site-packages",
        ".venv",
        "venv",
        ".tox",
        "__pypackages__",
        "node_modules",
    }
)


class NoWorktreeFound(RuntimeError):
    """Raised by find_worktree_root when no .git directory can be found walking up."""


def find_worktree_root(start_path: Path) -> Path:
    """Walk up from start_path until a .git directory or .git file is found.

    Returns the directory that contains .git.
    Raises NoWorktreeFound when the filesystem root is reached without finding one.
    """
    current = Path(start_path).resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root — build an actionable error listing
            # the start path's immediate subdirectories as candidate worktrees.
            start_resolved = Path(start_path).resolve()
            nearby = [
                d.name
                for d in start_resolved.iterdir()
                if d.is_dir()
            ] if start_resolved.is_dir() else []
            hint = (
                f"Nearby directories: {', '.join(nearby[:5])}" if nearby else ""
            )
            raise NoWorktreeFound(
                f"No git worktree found searching up from {start_path}. "
                f"{hint} Use --repo PATH to specify the worktree explicitly, "
                f"or cd into a worktree before running atdd coach."
            )
        current = parent


def resolve_repo_path(
    explicit_path: Optional[Path],
    cwd: Path,
) -> Path:
    """Return explicit_path if given; otherwise find the nearest git worktree root."""
    if explicit_path is not None:
        return Path(explicit_path)
    return find_worktree_root(cwd)


def find_existing_worktree_for_branch(branch: str, repo_root: Path) -> Optional[Path]:
    """Return the path of an existing worktree tracking *branch*, or None.

    Parses ``git worktree list --porcelain`` output to detect an existing worktree
    so the coach can reuse it instead of calling ``git worktree add`` again.
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        return None
    if result.returncode != 0:
        return None

    worktree_path: Optional[str] = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            worktree_path = line[len("worktree "):].strip()
        elif line.startswith("branch "):
            raw_branch = line[len("branch "):].strip()
            # Normalise refs/heads/feat/slug → feat/slug
            if raw_branch.startswith("refs/heads/"):
                raw_branch = raw_branch[len("refs/heads/"):]
            if raw_branch == branch and worktree_path is not None:
                return Path(worktree_path)
    return None


def ensure_issue_worktree(
    branch: str,
    repo_root: Path,
    target_path: Path,
) -> Path:
    """Ensure a worktree for *branch* exists at *target_path*.

    If a worktree already tracks *branch* (detected via git worktree list),
    reuse it and log the reuse.  Otherwise call ``git worktree add``.
    """
    existing = find_existing_worktree_for_branch(branch, repo_root)
    if existing is not None:
        print(
            f"[coach] Reusing existing worktree at {existing} for branch {branch!r}",
            flush=True,
        )
        return existing
    subprocess.run(
        ["git", "worktree", "add", str(target_path), branch],
        cwd=str(repo_root),
        check=True,
    )
    return target_path


def is_atdd_source_repo() -> bool:
    """
    Return True only when running inside the atdd source repo
    (editable / source checkout), False in any consumer install.

    Dogfood tests — tests that assert behavior against fixtures shipped
    inside `src/atdd/**/validators/fixtures/` — must call this and
    `pytest.skip(...)` when it returns False. Otherwise those tests leak
    into consumer `atdd validate coder` runs and fail with assertion
    errors against toolkit fixture data (see #272, #276).
    """
    try:
        import atdd  # local import to avoid cycles at module import time

        pkg_dir = Path(atdd.__file__).resolve().parent
    except (ImportError, AttributeError, TypeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return False

    if any(part in _VENDORED_PATH_MARKERS for part in pkg_dir.parts):
        return False

    try:
        repo_root = find_repo_root().resolve()
    except RuntimeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return False

    try:
        pkg_dir.relative_to(repo_root)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return False

    # Source repo always has a top-level pyproject.toml whose [project].name
    # is "atdd" — the strongest signal that we are actually in the toolkit
    # checkout and not in a consumer repo that happens to vendor atdd.
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return False
    return 'name = "atdd"' in text
