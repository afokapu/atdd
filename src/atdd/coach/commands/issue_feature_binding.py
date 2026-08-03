# Component: component:govern-lifecycle:bind-issue-feature:IssueFeatureBinding:backend:application
"""Plan-backed WMBT resolution and binding backfill (#1635).

Replaces the decommissioned lookup. ``issue_lifecycle._fetch_sub_issues`` used to
shell out to ``gh issue list --label atdd-wmbt --search "wmbt:<slug> in:title"``
and never read ``plan/``; #1477 removed the command that minted those labels with
no replacement, so every issue in the repo reported "WMBTs: none found" however
well decomposed it was. Resolution now walks
``issue -> stored feature URN -> feature YAML -> its wmbts: list``, entirely off
disk with no provider call.

Three outcomes are kept DISTINCT, because collapsing them into one blank line is
the whole defect: an issue with no binding, an issue whose binding names a
feature ``plan/`` does not contain, and an issue whose feature genuinely declares
no WMBTs are different situations and must read differently.

BOUNDARY: the plan-resolution primitive lives planner-side
(``atdd.planner.commands.feature_binding``) because the write-side guard in
``author_publish`` needs it too and the planner tree may not import
``atdd.coach``. This module DELEGATES there — coach → planner, never the reverse.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from atdd.planner.commands.feature_binding import (
    feature_in_body,
    resolve_feature,
    wmbt_paths,
)

logger = logging.getLogger(__name__)

GITHUB_PROVIDER = "github"
ISSUE_REF_KIND = "issue"


@dataclass(frozen=True)
class WmbtResolution:
    """The outcome of resolving one issue's WMBTs through its feature binding."""

    issue_number: int
    resolved: bool
    reason: Optional[str] = None          # None | "unbound" | "unresolved"
    feature: Optional[str] = None
    wmbts: List[str] = field(default_factory=list)
    paths: Dict[str, Path] = field(default_factory=dict)
    detail: str = ""


@dataclass(frozen=True)
class BackfillReport:
    """What a backfill run wrote, and what it refused to guess at."""

    written: Tuple[int, ...] = ()
    unresolved: Tuple[int, ...] = ()


def _open_store(control_root: Optional[Path]):
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    return StateStore(connect(init_state_store(start=control_root)))


def _work_item_for_issue(store, issue_number: int):
    ref = store.external_refs.resolve(GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number))
    if ref is None:
        return None
    return store.objects.get(ref.object_uid)


def resolve_wmbts_for_issue(
    issue_number: int, *, control_root: Optional[Path] = None
) -> WmbtResolution:
    """Resolve an issue's WMBTs through its stored feature binding.

    Reads the State Store and ``plan/`` off disk. Makes no subprocess call and no
    provider request — that independence is the point, not an optimisation: the
    lookup this replaces returned an empty list whenever its ``gh`` invocation
    failed, which is indistinguishable from a correct empty answer.
    """
    store = _open_store(control_root)
    obj = _work_item_for_issue(store, issue_number)
    if obj is None:
        return WmbtResolution(
            issue_number=issue_number, resolved=False, reason="unbound",
            detail=(
                f"github issue #{issue_number} is not registered in the State "
                f"Store, so it carries no feature binding"
            ),
        )

    declared = (obj.data or {}).get("feature")
    verdict = resolve_feature(declared, control_root)

    if verdict.reason == "unbound":
        return WmbtResolution(
            issue_number=issue_number, resolved=False, reason="unbound",
            detail=f"issue #{issue_number} carries no feature binding",
        )
    if not verdict.resolved:
        # A malformed URN (a train identity, say) and one absent from plan/ are
        # both "the declaration does not lead anywhere"; the detail distinguishes
        # them for a reader without multiplying caller-visible states.
        return WmbtResolution(
            issue_number=issue_number, resolved=False, reason="unresolved",
            feature=declared, detail=verdict.detail,
        )

    return WmbtResolution(
        issue_number=issue_number, resolved=True, reason=None,
        feature=verdict.urn, wmbts=list(verdict.wmbts),
        paths=wmbt_paths(verdict.wmbts, control_root),
        detail=verdict.detail,
    )


def render_wmbt_section(resolution: WmbtResolution) -> str:
    """The operator-facing WMBT block for `atdd coach enter`.

    Never renders "none found". That single string stood for four different
    states — well decomposed, undecomposed, unbound, and broken lookup — which is
    why the defect read as a decomposition gap for months.
    """
    if resolution.reason == "unbound":
        return (
            "  WMBTs: no feature binding — this issue declares no feature, so its "
            "decomposition cannot be located.\n"
            "         Set one: atdd author issue --revise "
            f"{resolution.issue_number} --feature <urn>"
        )
    if resolution.reason == "unresolved":
        return (
            f"  WMBTs: feature {resolution.feature} does not resolve in plan/ — "
            "the binding is broken, not absent.\n"
            f"         {resolution.detail}"
        )
    if not resolution.wmbts:
        return (
            f"  WMBTs: 0 declared by {resolution.feature} — the feature resolves "
            "but has no decomposition yet."
        )

    lines = [f"  WMBTs: {len(resolution.wmbts)} declared by {resolution.feature}"]
    for urn in resolution.wmbts:
        path = resolution.paths.get(urn)
        suffix = f"  ({path})" if path is not None else ""
        lines.append(f"    - {urn}{suffix}")
    return "\n".join(lines)


def backfill_feature_bindings(
    *, control_root: Optional[Path] = None, dry_run: bool = False
) -> BackfillReport:
    """Populate ``data.feature`` for work items that carry none.

    Derives ONLY from a body ``Feature`` row that resolves against ``plan/``.
    Anything else — a train identity in the Feature slot, a URN naming no
    feature, no declaration at all — is reported as unresolved and left NULL.
    Guessing here would manufacture a binding out of exactly the drift the
    backfill exists to find.

    Idempotent: a work item that already carries a feature is never overwritten,
    so a second run writes nothing and reports the same unresolved set.
    """
    from atdd.state.work_item_writer import revise_work_item_issue

    store = _open_store(control_root)
    written: List[int] = []
    unresolved: List[int] = []

    for ref in _issue_refs(store):
        obj = store.objects.get(ref.object_uid)
        if obj is None:
            continue
        data: Dict[str, Any] = obj.data or {}
        if data.get("feature"):
            continue  # already bound — never overwrite

        issue_number = int(ref.ref_value)
        candidate = feature_in_body(data.get("body"))
        if candidate is None or not resolve_feature(candidate, control_root).resolved:
            unresolved.append(issue_number)
            continue

        if not dry_run:
            revise_work_item_issue(store.conn, issue_number, feature=candidate)
        written.append(issue_number)

    return BackfillReport(written=tuple(sorted(written)), unresolved=tuple(sorted(unresolved)))


def _issue_refs(store) -> List[Any]:
    """Every ``github/issue`` external ref in the store."""
    rows = store.conn.execute(
        "SELECT object_uid, ref_value FROM external_refs "
        "WHERE provider = ? AND ref_kind = ?",
        (GITHUB_PROVIDER, ISSUE_REF_KIND),
    ).fetchall()

    @dataclass(frozen=True)
    class _Ref:
        object_uid: str
        ref_value: str

    return [_Ref(object_uid=r[0], ref_value=r[1]) for r in rows]
