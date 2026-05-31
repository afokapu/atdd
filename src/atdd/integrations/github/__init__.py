"""GitHub integration adapter (docs/coach-decomposition.md §4.10).

Owns issue labels, Projects v2 fields, PR state/merge, and check runs. Every
function shells out to the ``gh`` CLI and returns **plain data** — strings or the
local dataclasses in :mod:`atdd.integrations.github.types`. It never returns
Coach-core types and never imports ``atdd.coach.*`` / ``atdd.train.*`` /
``atdd.runtime.*`` (§3.3, import-discipline gate). The translation of this plain
data into Coach-core ``Evidence`` happens in ``train.persistence`` (Child 7).

Public surface (re-exported for callers/shims):

* ``issue_state`` — phase label read + atomic ``transition_phase`` (closes #882)
* ``projects_v2`` — ``sync_status_field`` (GraphQL; requires ``PROJECT_TOKEN``)
* ``pr`` — PR state/open/merge/update-branch
* ``checks`` — check-run reads + rerun trigger
"""
from atdd.integrations.github import checks, issue_state, pr, projects_v2
from atdd.integrations.github.types import (
    CheckRunData,
    GitHubIntegrationError,
    MergeResult,
    MissingProjectTokenError,
    PrStateData,
    ReviewData,
)

__all__ = [
    "issue_state",
    "projects_v2",
    "pr",
    "checks",
    "CheckRunData",
    "GitHubIntegrationError",
    "MergeResult",
    "MissingProjectTokenError",
    "PrStateData",
    "ReviewData",
]
