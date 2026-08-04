# Component: component:govern-lifecycle:bind-issue-train:StoreIssueRows:backend:integration
"""Read every issue-backed work item out of the local State Store (#1590).

One reader, two scanners. ``issue_feature_binding_scanner`` and
``issue_train_binding_scanner`` both need the same thing — the flattened
``(issue number, lifecycle state, data)`` rows for every work item carrying a
GitHub issue ``external_ref`` — and had it written twice, which is what
``coder.refactor.quality-duplication`` reports and what would have let the two
scanners drift apart on which records they consider at all.

Store-only by design: no GitHub call, so a validator built on this needs neither
the ``github_api`` nor the ``platform`` marker and is therefore SELECTED by
``atdd validate coach --local --skip-api`` rather than silently deselected by its
marker expression.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

__all__ = ["issue_backed_rows"]


def issue_backed_rows(
    control_root: Optional[Path] = None,
    *,
    fields: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """``[{number, status, **fields}]`` for every issue-backed work item.

    ``number`` is the GitHub issue number (as stored, a string) and ``status`` the
    work item's lifecycle state. Each name in ``fields`` is lifted out of the
    work item's JSON ``data`` — the caller names what it needs rather than
    receiving the whole payload, so a scan does not carry issue bodies it will
    never read.
    """
    from atdd.coach.commands.issue_feature_binding import (
        GITHUB_PROVIDER, ISSUE_REF_KIND, _open_store,
    )

    store = _open_store(control_root)
    rows = store.conn.execute(
        "SELECT r.ref_value, o.state, o.data FROM external_refs r "
        "JOIN objects o ON o.uid = r.object_uid "
        "WHERE r.provider = ? AND r.ref_kind = ?",
        (GITHUB_PROVIDER, ISSUE_REF_KIND),
    ).fetchall()

    wanted = tuple(fields)
    issues: List[Dict[str, Any]] = []
    for ref_value, state, data in rows:
        payload = json.loads(data) if data else {}
        record: Dict[str, Any] = {"number": ref_value, "status": state}
        record.update({name: payload.get(name) for name in wanted})
        issues.append(record)
    return issues
