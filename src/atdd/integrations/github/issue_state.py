"""GitHub issue phase/label + body adapter (docs/coach-decomposition.md §4.10).

``transition_phase`` is the **single owner** of the atomic label-swap +
Projects v2 status sync. Because both writes live behind one call, the label and
the board can never drift — that lock-step is the structural fix for #882.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from atdd.integrations.github import _gh, projects_v2
from atdd.integrations.github.types import MissingProjectTokenError

_log = logging.getLogger(__name__)

_PHASE_LABEL_PREFIX = "atdd:"
_ISSUE_LABEL = "atdd-issue"


def _phase_from_labels(labels: list[str]) -> Optional[str]:
    for name in labels:
        if name.startswith(_PHASE_LABEL_PREFIX) and name != _ISSUE_LABEL:
            return name[len(_PHASE_LABEL_PREFIX):]
    return None


def read_phase(issue: int) -> Optional[str]:
    """Return the phase string from the live ``atdd:<phase>`` label, or None."""
    out = _gh.run_gh(
        ["issue", "view", str(issue), "--json", "labels",
         "--jq", "[.labels[].name]"]
    )
    labels = json.loads(out) if out else []
    return _phase_from_labels(labels)


def _current_phase_labels(issue: int) -> list[str]:
    out = _gh.run_gh(
        ["issue", "view", str(issue), "--json", "labels",
         "--jq", "[.labels[].name]"]
    )
    labels = json.loads(out) if out else []
    return [
        name for name in labels
        if name.startswith(_PHASE_LABEL_PREFIX) and name != _ISSUE_LABEL
    ]


def transition_phase(
    issue: int, to: str, *, repo_root: Optional[Path] = None
) -> None:
    """Swap the ``atdd:<phase>`` label to *to* AND sync the Projects v2 board.

    ATOMIC contract (§4.10): one call site owns both writes so they cannot
    drift — the #882 fix. The label swap always runs. The board sync is routed
    through :func:`projects_v2.sync_status_field`, which requires
    ``PROJECT_TOKEN``; when the token is absent or Projects access is denied
    (#384) the swap still lands and a loud warning is logged (label-only sync),
    preserving the established graceful-degradation behaviour.
    """
    stale = _current_phase_labels(issue)
    for label in stale:
        if label == f"{_PHASE_LABEL_PREFIX}{to}":
            continue
        _gh.run_gh(["issue", "edit", str(issue), "--remove-label", label])
    _gh.run_gh(
        ["issue", "edit", str(issue), "--add-label", f"{_PHASE_LABEL_PREFIX}{to}"]
    )

    try:
        projects_v2.sync_status_field(issue, to, repo_root=repo_root)
    except MissingProjectTokenError as exc:
        _log.warning(
            "Projects v2 status sync skipped (label-only): PROJECT_TOKEN unset",
            extra={"issue": issue, "phase": to, "error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001 - degrade on access-denied, re-raise else
        if _gh.is_access_denied(exc):
            _log.warning(
                "Projects v2 status sync denied (label-only); set PROJECT_TOKEN. "
                "See docs/operator-projects-v2-token.md",
                extra={"issue": issue, "phase": to, "error": str(exc)},
            )
        else:
            raise


def read_train(issue: int) -> Optional[str]:
    """Return the ATDD Train value from the issue body metadata table, or None."""
    body = read_body(issue)
    m = re.search(r"\|\s*Train\s*\|\s*([^|]+)\|", body)
    if not m:
        return None
    value = m.group(1).strip().strip("`")
    if not value or value.upper() == "TBD":
        return None
    return value


def set_train(issue: int, train_id: str) -> None:
    """Persist *train_id* as a label hint (``atdd-train:<id>``).

    The canonical Train value lives in the Projects v2 ``ATDD Train`` text field
    and the issue-body table; this adapter records the lightweight label so a
    pure label read can recover lineage. Project-field writes go through the
    Projects v2 adapter from the train layer (Child 7).
    """
    _gh.run_gh(
        ["issue", "edit", str(issue), "--add-label", f"atdd-train:{train_id}"]
    )


def read_body(issue: int) -> str:
    """Return the raw issue body markdown."""
    out = _gh.run_gh(
        ["issue", "view", str(issue), "--json", "body", "--jq", ".body"]
    )
    return out or ""


def update_body(issue: int, body: str) -> None:
    """Replace the issue body with *body*."""
    _gh.run_gh(
        ["issue", "edit", str(issue), "--body-file", "-"], input_text=body
    )


__all__ = [
    "read_phase",
    "transition_phase",
    "read_train",
    "set_train",
    "read_body",
    "update_body",
]
