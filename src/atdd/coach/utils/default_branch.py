"""
Default-branch resolver shared by ``atdd branch`` and ``atdd pr``.

Resolution order:
    1. ``.atdd/config.yaml::github.default_branch`` if present.
    2. ``gh repo view --json defaultBranchRef --jq .defaultBranchRef.name``.
    3. Literal ``"main"`` with a ``::warning::`` log.

Cross-coordination: introduced for issues #477 and #478. First-mover wins;
both PRs converge on this single canonical home so the literal ``"main"``
hardcode disappears from ``branch.py:73`` and ``pr.py:478``.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


def resolve_default_branch(repo_root: Optional[Path] = None) -> str:
    """Resolve the repository's default branch name.

    Args:
        repo_root: Repo root containing ``.atdd/config.yaml``. Defaults to cwd.

    Returns:
        Branch name string (e.g. ``"main"``).
    """
    root = repo_root or Path.cwd()

    cfg_default = _read_config_default_branch(root / ".atdd" / "config.yaml")
    if cfg_default:
        return cfg_default

    gh_default = _query_gh_default_branch(root)
    if gh_default:
        return gh_default

    print("::warning::default-branch resolver fell back to literal 'main'")
    logger.warning(
        "default-branch resolver fell back to literal 'main'",
        extra={"action": "default_branch_fallback"},
    )
    return "main"


def _read_config_default_branch(config_file: Path) -> Optional[str]:
    if not config_file.exists():
        return None
    try:
        data = yaml.safe_load(config_file.read_text()) or {}
    except yaml.YAMLError:
        return None
    value = (data.get("github") or {}).get("default_branch")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _query_gh_default_branch(cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef",
             "--jq", ".defaultBranchRef.name"],
            capture_output=True, text=True, timeout=10,
            cwd=cwd,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    return name or None
