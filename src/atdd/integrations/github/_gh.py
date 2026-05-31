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
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import yaml

from atdd.integrations.github.types import GitHubIntegrationError

_log = logging.getLogger(__name__)

#: Env var holding the fine-grained PAT with Projects: R/W (issue #404 / #882).
PROJECT_TOKEN_ENV = "PROJECT_TOKEN"


@dataclass(frozen=True)
class ProjectRef:
    """Repo + Projects v2 identifiers read from ``.atdd/config.yaml``."""

    repo: str
    project_id: str


def project_token() -> Optional[str]:
    """Return the ``PROJECT_TOKEN`` PAT if set and non-empty, else ``None``."""
    token = os.environ.get(PROJECT_TOKEN_ENV, "").strip()
    return token or None


def run_gh(
    args: Sequence[str],
    *,
    token: Optional[str] = None,
    input_text: Optional[str] = None,
    timeout: int = 30,
) -> str:
    """Run a ``gh`` command and return stripped stdout.

    When *token* is given it is injected as ``GH_TOKEN`` for that invocation only
    (used to route Projects v2 mutations through ``PROJECT_TOKEN``). Raises
    :class:`GitHubIntegrationError` on a non-zero exit or a missing ``gh`` binary.
    """
    cmd = ["gh", *args]
    env = None
    if token:
        env = {**os.environ, "GH_TOKEN": token}
    _log.debug("gh %s", " ".join(args), extra={"command": args[0] if args else "gh"})
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            env=env,
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


def graphql(query: str, *, token: Optional[str] = None) -> dict:
    """Execute a GraphQL query/mutation via ``gh api graphql``.

    Raises :class:`GitHubIntegrationError` on transport failure or a GraphQL
    ``errors`` block (so callers can distinguish access-denied responses).
    """
    output = run_gh(["api", "graphql", "-f", f"query={query}"], token=token)
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


def resolve_project_config(repo_root: Optional[Path] = None) -> ProjectRef:
    """Read ``repo`` + ``project_id`` from ``.atdd/config.yaml``.

    Raises :class:`GitHubIntegrationError` when the config or its ``github``
    section is missing — the same loud-fail contract the old ``ProjectConfig``
    used, so callers see an actionable message instead of a silent no-op.
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
    project_id = github.get("project_id")
    if not repo or not project_id:
        raise GitHubIntegrationError(
            "Missing github.repo / github.project_id in .atdd/config.yaml"
        )
    return ProjectRef(repo=str(repo), project_id=str(project_id))


def is_access_denied(exc: Exception) -> bool:
    """True when *exc* is the Projects v2 access-denied response (issue #384)."""
    return "resource not accessible by integration" in str(exc).lower()
