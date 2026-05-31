"""GitHub Projects v2 field sync (docs/coach-decomposition.md §4.10).

``sync_status_field`` is the dedicated, ``PROJECT_TOKEN``-authenticated mutation
that closes #882: the old status sync was a best-effort side-effect routed
through the default token, which cannot write Projects v2 in CI (#404), so the
board silently drifted from the label. Routing every status write through this
one PAT-backed call makes the board update actually land.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from atdd.integrations.github import _gh
from atdd.integrations.github.types import (
    GitHubIntegrationError,
    MissingProjectTokenError,
)

_log = logging.getLogger(__name__)

#: Name of the Projects v2 single-select field tracking ATDD phase.
STATUS_FIELD_NAME = "ATDD Status"


def _resolve_item_id(issue: int, cfg: _gh.ProjectRef, token: str) -> str:
    """Return the project item id for *issue*, or raise if not on the board."""
    owner, name = cfg.repo.split("/", 1)
    data = _gh.graphql(
        f'{{ repository(owner:"{owner}", name:"{name}") {{ '
        f'issue(number:{issue}) {{ '
        f'projectItems(first: 20) {{ nodes {{ id project {{ id }} }} }} '
        f'}} }} }}',
        token=token,
    )
    issue_node = (
        data.get("data", {}).get("repository", {}).get("issue") or {}
    )
    for item in issue_node.get("projectItems", {}).get("nodes", []):
        if (item.get("project") or {}).get("id") == cfg.project_id:
            return item["id"]
    raise GitHubIntegrationError(
        f"issue #{issue} is not on project {cfg.project_id}"
    )


def _resolve_status_option(cfg: _gh.ProjectRef, phase: str, token: str) -> tuple[str, str]:
    """Return ``(field_id, option_id)`` for the ``ATDD Status`` value *phase*."""
    data = _gh.graphql(
        f'{{ node(id: "{cfg.project_id}") {{ ... on ProjectV2 {{ '
        f'fields(first: 30) {{ nodes {{ '
        f'... on ProjectV2SingleSelectField {{ id name options {{ id name }} }} '
        f'}} }} }} }} }}',
        token=token,
    )
    nodes = (
        data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
    )
    for node in nodes:
        if node.get("name") == STATUS_FIELD_NAME:
            for opt in node.get("options", []):
                if opt.get("name") == phase:
                    return node["id"], opt["id"]
            raise GitHubIntegrationError(
                f"{STATUS_FIELD_NAME!r} has no option {phase!r}"
            )
    raise GitHubIntegrationError(
        f"project {cfg.project_id} has no {STATUS_FIELD_NAME!r} field"
    )


def sync_status_field(
    issue: int, phase: str, *, repo_root: Optional[Path] = None
) -> None:
    """Set the Projects v2 ``ATDD Status`` field for *issue* to *phase*.

    GraphQL mutation against Projects v2. **Requires ``PROJECT_TOKEN``** — the
    default ``GITHUB_TOKEN`` cannot write Projects v2 (#404). Idempotent: safe to
    call repeatedly with the same value.

    Raises :class:`MissingProjectTokenError` when ``PROJECT_TOKEN`` is unset and
    :class:`GitHubIntegrationError` on any other adapter failure.
    """
    token = _gh.project_token()
    if not token:
        raise MissingProjectTokenError(
            "PROJECT_TOKEN not set — cannot sync Projects v2 status field. "
            "See docs/operator-projects-v2-token.md."
        )
    cfg = _gh.resolve_project_config(repo_root)
    item_id = _resolve_item_id(issue, cfg, token)
    field_id, option_id = _resolve_status_option(cfg, phase, token)
    _gh.graphql(
        f'mutation {{ updateProjectV2ItemFieldValue(input: {{ '
        f'projectId: "{cfg.project_id}", itemId: "{item_id}", '
        f'fieldId: "{field_id}", value: {{ singleSelectOptionId: "{option_id}" }} '
        f'}}) {{ projectV2Item {{ id }} }} }}',
        token=token,
    )
    _log.info(
        "Synced Projects v2 status field",
        extra={"issue": issue, "phase": phase},
    )


__all__ = ["sync_status_field", "STATUS_FIELD_NAME"]
