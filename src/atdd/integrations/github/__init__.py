"""GitHub integration adapter (docs/coach-decomposition.md §4.10).

Owns issue labels, PR state/merge, and check runs. Every function shells out to
the ``gh`` CLI and returns **plain data** — strings or the local dataclasses in
:mod:`atdd.integrations.github.types`. It never returns Coach-core types and
never imports ``atdd.coach.*`` / ``atdd.train.*`` / ``atdd.runtime.*`` (§3.3,
import-discipline gate). The translation of this plain data into Coach-core
``Evidence`` happens in ``train.persistence`` (Child 7).

The lifecycle state machine runs on the ``atdd:<phase>`` issue label (REST) plus
the local ``.atdd/manifest.yaml`` mirror; the Projects v2 board sync was
decommissioned in #1051.

Public surface (re-exported for callers/shims):

* ``issue_state`` — phase label read + label-only ``transition_phase``
* ``pr`` — PR state/open/merge/update-branch
* ``checks`` — check-run reads + rerun trigger
"""
from atdd.integrations.github import checks, issue_state, pr
from atdd.integrations.github.types import (
    CheckRunData,
    GitHubIntegrationError,
    MergeResult,
    PrStateData,
    ReviewData,
)

__all__ = [
    "issue_state",
    "pr",
    "checks",
    "CheckRunData",
    "GitHubIntegrationError",
    "MergeResult",
    "PrStateData",
    "ReviewData",
]
