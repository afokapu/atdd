"""GitHub issue phase/label + body adapter (docs/coach-decomposition.md §4.10).

``transition_phase`` swaps the ``atdd:<phase>`` label (REST). That label, plus
the local ``.atdd/manifest.yaml`` mirror, is the sole representation of lifecycle
state — the Projects v2 board sync was decommissioned in #1051.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from atdd.integrations.github import _gh

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
    """Swap the ``atdd:<phase>`` label to *to* (REST).

    The label is the authoritative phase representation (#1051); the local
    manifest mirror records the same transition. No Projects v2 board write.
    """
    stale = _current_phase_labels(issue)
    for label in stale:
        if label == f"{_PHASE_LABEL_PREFIX}{to}":
            continue
        _gh.run_gh(["issue", "edit", str(issue), "--remove-label", label])
    _gh.run_gh(
        ["issue", "edit", str(issue), "--add-label", f"{_PHASE_LABEL_PREFIX}{to}"]
    )


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
