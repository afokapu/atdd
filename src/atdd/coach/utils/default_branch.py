"""Resolve the canonical default branch for the current repository.

Resolution order (issue #477, shared with #478):
  1. ``.atdd/config.yaml::github.default_branch`` if present.
  2. ``gh repo view --json defaultBranchRef --jq .defaultBranchRef.name``.
  3. Literal ``"main"`` with a ``::warning::`` log line.

The helper is the canonical default-branch source for both
``atdd pr`` (#477) and ``atdd branch`` (#478). Hardcoded ``"main"``
in those call sites is a known-bad pattern that breaks consumer
repos whose default is ``master`` or another name.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_FALLBACK = "main"


def _read_from_config(repo_root: Path) -> Optional[str]:
    cfg_path = repo_root / ".atdd" / "config.yaml"
    if not cfg_path.is_file():
        return None
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning(
            "Failed to parse %s: %s",
            cfg_path, exc,
            extra={"path": str(cfg_path), "error": str(exc)},
        )
        return None
    value = (data.get("github") or {}).get("default_branch")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_from_gh(repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["gh", "repo", "view",
             "--json", "defaultBranchRef",
             "--jq", ".defaultBranchRef.name"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_root,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning(
            "gh repo view failed: %s",
            exc,
            extra={"error": str(exc)},
        )
        return None
    if result.returncode != 0:
        logger.warning(
            "gh repo view returned %d: %s",
            result.returncode, result.stderr.strip(),
            extra={"stderr": result.stderr.strip(), "returncode": result.returncode},
        )
        return None
    name = result.stdout.strip()
    return name or None


def resolve_default_branch(repo_root: Optional[Path] = None) -> str:
    """Return the repo's default branch name.

    Resolves via ``.atdd/config.yaml::github.default_branch`` first,
    then ``gh repo view``, then ``"main"`` as the final fallback.

    Args:
        repo_root: Repo root for config + gh CLI cwd. Defaults to ``Path.cwd()``.

    Returns:
        The default branch name (never empty).
    """
    root = repo_root or Path.cwd()

    from_config = _read_from_config(root)
    if from_config:
        return from_config

    from_gh = _read_from_gh(root)
    if from_gh:
        return from_gh

    logger.warning(
        "::warning::default-branch resolution fell back to '%s' "
        "(no .atdd/config.yaml::github.default_branch and gh repo view failed)",
        _FALLBACK,
        extra={"fallback": _FALLBACK, "repo_root": str(root)},
    )
    return _FALLBACK
