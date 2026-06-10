"""Internal ``gh`` CLI helpers for the GitHub integration layer.

LAYERING: this package may import only stdlib + ``subprocess`` + ``json``
(docs/coach-decomposition.md §3.3). It MUST NOT import ``atdd.coach.*`` —
including ``atdd.coach.github.GitHubClient`` — so the ``gh`` plumbing is
re-implemented thinly here rather than reused. ``PyYAML`` is a third-party config
parser, not an ``atdd`` layer, so reading ``.atdd/config.yaml`` is allowed.

Tests patch :func:`run_gh` / :func:`graphql` to return canned ``gh`` JSON, so the
adapter is exercised with **no live API** (§13.4 acceptance).
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Sequence

import yaml

from atdd.integrations.github.types import GitHubIntegrationError

_log = logging.getLogger(__name__)


def run_gh(
    args: Sequence[str],
    *,
    input_text: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Run a ``gh`` command and return stripped stdout.

    Raises :class:`GitHubIntegrationError` on a non-zero exit or a missing
    ``gh`` binary.
    """
    cmd = ["gh", *args]
    _log.debug("gh %s", " ".join(args), extra={"command": args[0] if args else "gh"})
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
    except FileNotFoundError as exc:
        raise GitHubIntegrationError(
            "gh CLI not found. Install: https://cli.github.com"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitHubIntegrationError(
            f"gh command timed out after {timeout}s: {' '.join(args)}"
        ) from exc
    if result.returncode != 0:
        raise GitHubIntegrationError(
            f"gh command failed: {' '.join(args)}\nstderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def graphql(query: str) -> dict:
    """Execute a GraphQL query/mutation via ``gh api graphql``.

    Raises :class:`GitHubIntegrationError` on transport failure or a GraphQL
    ``errors`` block.
    """
    output = run_gh(["api", "graphql", "-f", f"query={query}"])
    data = json.loads(output) if output else {}
    if isinstance(data, dict) and data.get("errors"):
        raise GitHubIntegrationError(
            f"GraphQL error: {json.dumps(data['errors'])}"
        )
    return data


def _find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk up from *start* (or cwd) to the dir containing ``.atdd/config.yaml``."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".atdd" / "config.yaml").is_file():
            return candidate
    return None


def resolve_repo(repo_root: Optional[Path] = None) -> str:
    """Read the ``repo`` (``owner/name``) from ``.atdd/config.yaml``.

    The Projects v2 board was decommissioned in #1051, so only the repo slug is
    resolved now (no board identifiers). Raises :class:`GitHubIntegrationError`
    when the config or its ``github.repo`` is missing.
    """
    root = repo_root or _find_repo_root()
    if root is None:
        raise GitHubIntegrationError(
            ".atdd/config.yaml not found (run 'atdd init' first)"
        )
    config_path = root / ".atdd" / "config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text()) or {}
    except OSError as exc:
        raise GitHubIntegrationError(
            f"Could not read {config_path}"
        ) from exc
    github = config.get("github") or {}
    repo = github.get("repo")
    if not repo:
        raise GitHubIntegrationError(
            "Missing github.repo in .atdd/config.yaml"
        )
    return str(repo)
