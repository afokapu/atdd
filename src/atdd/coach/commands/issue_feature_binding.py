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

WHICH TREE ANSWERS (#1732/#1750). A fourth outcome joined them: the lookup could
not see the issue's context at all. Resolution used to read ``plan/`` under
whatever directory the command was executing in, so the banner answered a
question about the operator's cwd while appearing to answer one about the issue.
Measured 2026-08-05 on ``#1735``: its banner listed ``C021`` — authored on
``#1670``'s branch and absent from ``#1735``'s — and omitted ``C020``, which
``#1735``'s own commit created; every path printed was rooted in a third
worktree. The plan tree is now resolved through the issue's STORE BINDING
(:func:`resolve_plan_tree`), and when that tree cannot be located the lookup says
so instead of quietly reading the cwd's copy — showing the wrong file silently is
worse than admitting the path is unresolvable (#1719).

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


#: How :func:`resolve_plan_tree` found the tree it answered from. Kept as data
#: rather than inferred from ``root is None`` because the render must say WHICH
#: tree answered — a count computed from an unrelated checkout printed as a bare
#: number is the #1732 defect even when the number happens to be right.
TREE_OWN_WORKTREE = "own-worktree"    # the command is standing on the issue's branch
TREE_BINDING = "binding"              # located through the store's branch binding
TREE_UNLOCATED = "unlocated"          # the issue has a branch; no tree holds it
TREE_UNBOUND_BRANCH = "unbound-branch"  # the issue records no branch to resolve through
TREE_NO_VCS = "no-vcs"                # no git working tree — nothing to resolve across
TREE_NO_GIT = "no-git"                # git itself could not be run


@dataclass(frozen=True)
class PlanTree:
    """The tree an issue's ``plan/`` was resolved against, and how it was found.

    Modelled on ``#1376``'s :class:`~atdd.coach.gate.approval_paths.ApprovalTokenLocation`,
    which made an artefact's location explicit and gave the resolution an
    observable flag so a fallback is visible rather than silent. Same demand
    here: ``source`` is the observable, and a caller must be able to tell "this
    is the issue's own tree" from "this is whatever tree I was standing in"
    without parsing prose.

    ``root`` is ``None`` only for :data:`TREE_UNLOCATED` — the one state in which
    resolving anything at all would mean reading a tree we KNOW is not the
    issue's.

    ``qualification`` is the sentence a renderer must print alongside whatever it
    read, and it is carried HERE rather than derived from ``source`` at the
    render site: a state that answers from a tree it cannot vouch for has to
    arrive already saying so, or the next state added will arrive silent.
    """

    root: Optional[Path]
    branch: Optional[str]
    source: str
    detail: str = ""
    qualification: Optional[str] = None


@dataclass(frozen=True)
class WmbtResolution:
    """The outcome of resolving one issue's WMBTs through its feature binding."""

    issue_number: int
    resolved: bool
    # None | "unbound" | "unresolved" | "unlocated"
    reason: Optional[str] = None
    feature: Optional[str] = None
    wmbts: List[str] = field(default_factory=list)
    paths: Dict[str, Path] = field(default_factory=dict)
    detail: str = ""
    tree: Optional[PlanTree] = None


@dataclass(frozen=True)
class BackfillReport:
    """What a backfill run wrote, and what it refused to guess at.

    ``unrepairable`` is the third outcome (#1689): the work item DOES carry a
    stored feature, but that value does not resolve in ``plan/`` and the body
    offers nothing better. Those rows used to vanish — counted as "already
    bound" by a truthy check and reported in neither list — so an operator could
    run the backfill to completion and never learn the store held 156 bindings
    with values like ``TBD``, ``none`` and ``N/A``.
    """

    written: Tuple[int, ...] = ()
    unresolved: Tuple[int, ...] = ()
    unrepairable: Tuple[int, ...] = ()


def _open_store(control_root: Optional[Path]):
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    return StateStore(connect(init_state_store(start=control_root)))


def _work_item_for_issue(store, issue_number: int):
    ref = store.external_refs.resolve(GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number))
    if ref is None:
        return None
    return store.objects.get(ref.object_uid)


def resolve_plan_tree(
    issue_number: int, *, control_root: Optional[Path] = None
) -> PlanTree:
    """Locate the working tree whose ``plan/`` speaks for *issue_number*.

    Composed from two resolvers that ALREADY EXIST — nothing new is invented
    here, deliberately: ``#1755`` records seven separate branch/tree resolvers in
    this tree, two pairs of which share a name with incompatible signatures.

    * issue → branch: :meth:`atdd.coach.commands.issue.IssueManager._manifest_branch`,
      the store-backed read (``#1270`` slice D) over the ``data.branch`` binding
      ``BranchManager._record_binding_in_store`` writes at worktree-create time.
    * branch → tree: :func:`atdd.coach.utils.repo.find_existing_worktree_for_branch`,
      the ``git worktree list --porcelain`` parse the coach already uses to reuse
      a worktree instead of re-adding one.

    Six outcomes, because each is a genuinely different situation and collapsing
    any two of them is how this defect class keeps reappearing:

    ``no-vcs``
        ``control_root`` is not a git working tree (a hermetic tmp dir, a
        consumer repo before ``git init``). There are no other branches to be
        confused with, so the cwd's ``plan/`` is the only tree there is and is
        answered from unqualified. This is what keeps every pre-existing caller
        behaving exactly as it did.
    ``no-git``
        git could not be RUN — not on PATH, or unusable. Answered from the cwd
        like ``no-vcs``, because refusing here would turn a missing tool into an
        outage for a diagnostic, but QUALIFIED: unlike ``no-vcs`` this says
        nothing about whether sibling worktrees exist, only that we could not
        ask.
    ``own-worktree``
        The command is standing ON the issue's registered branch. Answered from
        ``control_root`` — the no-regression case #1750 names explicitly.
    ``binding``
        A different worktree holds the issue's branch. Answered from THERE.
    ``unbound-branch``
        The issue records no branch, so there is nothing to resolve through. The
        cwd still answers, but the caller MUST qualify it: printing a bare count
        computed from an unrelated tree is the defect even when no better tree
        exists (#1732 Decisions).
    ``unlocated``
        The issue records a branch and no tree on this machine holds it. Here we
        know for certain the cwd is NOT the issue's tree, so nothing is resolved
        and ``root`` is ``None``.
    """
    from atdd.coach.commands.issue import IssueManager
    from atdd.coach.utils.git import _current_branch
    from atdd.coach.utils.repo import find_existing_worktree_for_branch

    root = Path(control_root) if control_root is not None else Path.cwd()

    try:
        standing_on = _current_branch(root)
    except OSError as exc:
        # `_current_branch` tolerates a non-zero git, not an absent one. A banner
        # must not become an outage over a missing tool (the L003 smoke test holds
        # the whole enter path to that), so answer from here — and say that we
        # could not ask, which is NOT the same claim as "there are no branches".
        logger.warning(
            "git could not be run; the issue's own tree could not be located",
            extra={"issue": issue_number, "root": str(root), "error": str(exc)},
        )
        return PlanTree(
            root=root, branch=None, source=TREE_NO_GIT,
            detail=f"git could not be run from {root}: {exc}",
            qualification=(
                f"         Read from {root} — git could not be run, so this may "
                "not be the issue's own tree."
            ),
        )

    if standing_on is None:
        return PlanTree(
            root=root, branch=None, source=TREE_NO_VCS,
            detail=f"{root} is not a git working tree; plan/ resolves there",
        )

    branch = IssueManager(root)._manifest_branch(issue_number)
    if not branch:
        return PlanTree(
            root=root, branch=None, source=TREE_UNBOUND_BRANCH,
            detail=(
                f"issue #{issue_number} records no branch, so its own tree cannot "
                f"be located; read from {root}, which may not be the issue's"
            ),
            qualification=(
                f"         Read from {root} — this issue records no branch, so "
                "that may not be its own tree."
            ),
        )

    if branch == standing_on:
        return PlanTree(
            root=root, branch=branch, source=TREE_OWN_WORKTREE,
            detail=f"{root} is checked out on {branch}, the issue's own branch",
        )

    worktree = find_existing_worktree_for_branch(branch, root)
    if worktree is not None:
        return PlanTree(
            root=worktree, branch=branch, source=TREE_BINDING,
            detail=f"resolved through the store binding: {branch} at {worktree}",
        )

    return PlanTree(
        root=None, branch=branch, source=TREE_UNLOCATED,
        detail=(
            f"issue #{issue_number} is bound to {branch}, and no working tree on "
            f"this machine has it checked out — so its plan/ cannot be read from "
            f"here. {root} is checked out on {standing_on}, a different branch, "
            f"and its plan/ would answer for that branch instead"
        ),
    )


def resolve_wmbts_for_issue(
    issue_number: int, *, control_root: Optional[Path] = None
) -> WmbtResolution:
    """Resolve an issue's WMBTs through its stored feature binding.

    Reads the State Store and ``plan/`` off disk. Makes no subprocess call and no
    provider request — that independence is the point, not an optimisation: the
    lookup this replaces returned an empty list whenever its ``gh`` invocation
    failed, which is indistinguishable from a correct empty answer.

    ``control_root`` locates the STORE. The plan tree is a separate question and
    is answered by :func:`resolve_plan_tree` — conflating the two is what made
    the banner report on the operator's cwd (#1732/#1750).
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
    tree = resolve_plan_tree(issue_number, control_root=control_root)

    if tree.root is None:
        # Asked BEFORE resolve_feature, not after. The #1635 binding logic is
        # correct and would report "the binding is broken, not absent" — a
        # confident, precise and WRONG diagnosis when the only thing that is
        # broken is our ability to look. Reporting a plan-graph fault from an
        # unmade observation is the more dangerous direction of this defect.
        return WmbtResolution(
            issue_number=issue_number, resolved=False, reason="unlocated",
            feature=declared, detail=tree.detail, tree=tree,
        )

    verdict = resolve_feature(declared, tree.root)

    if verdict.reason == "unbound":
        return WmbtResolution(
            issue_number=issue_number, resolved=False, reason="unbound",
            detail=f"issue #{issue_number} carries no feature binding", tree=tree,
        )
    if not verdict.resolved:
        # A malformed URN (a train identity, say) and one absent from plan/ are
        # both "the declaration does not lead anywhere"; the detail distinguishes
        # them for a reader without multiplying caller-visible states.
        return WmbtResolution(
            issue_number=issue_number, resolved=False, reason="unresolved",
            feature=declared, detail=verdict.detail, tree=tree,
        )

    return WmbtResolution(
        issue_number=issue_number, resolved=True, reason=None,
        feature=verdict.urn, wmbts=list(verdict.wmbts),
        paths=wmbt_paths(verdict.wmbts, tree.root),
        detail=verdict.detail, tree=tree,
    )


def _tree_qualifier(tree: Optional[PlanTree]) -> List[str]:
    """The line naming whose tree answered, when the answer is not vouched for.

    Empty whenever the tree IS the issue's — a banner that qualified every
    reading would train the reader to skip the qualification.
    """
    if tree is None or not tree.qualification:
        return []
    return [tree.qualification]


def render_wmbt_section(resolution: WmbtResolution) -> str:
    """The operator-facing WMBT block for `atdd coach enter`.

    Never renders "none found". That single string stood for four different
    states — well decomposed, undecomposed, unbound, and broken lookup — which is
    why the defect read as a decomposition gap for months.

    Never renders a bare count computed from a tree that is not the issue's,
    either. A count the reader cannot attribute is the same defect wearing a
    number (#1732).
    """
    if resolution.reason == "unbound":
        return (
            "  WMBTs: no feature binding — this issue declares no feature, so its "
            "decomposition cannot be located.\n"
            "         Set one: atdd author issue --revise "
            f"{resolution.issue_number} --feature <urn>"
        )
    if resolution.reason == "unlocated":
        # Deliberately NOT the "binding is broken" sentence. Nothing about the
        # plan graph has been observed; the only fault established is that this
        # command cannot see the issue's tree, and it says exactly that.
        tree = resolution.tree
        branch = tree.branch if tree is not None else None
        return (
            f"  WMBTs: not resolved — this command cannot see #{resolution.issue_number}'s "
            f"tree, so its decomposition was not read.\n"
            f"         {resolution.detail}\n"
            f"         Give the branch a tree to read: atdd worktree create "
            f"{resolution.issue_number}   (branch: {branch})"
        )
    if resolution.reason == "unresolved":
        return "\n".join([
            f"  WMBTs: feature {resolution.feature} does not resolve in plan/ — "
            "the binding is broken, not absent.",
            f"         {resolution.detail}",
            *_tree_qualifier(resolution.tree),
        ])
    if not resolution.wmbts:
        return "\n".join([
            f"  WMBTs: 0 declared by {resolution.feature} — the feature resolves "
            "but has no decomposition yet.",
            *_tree_qualifier(resolution.tree),
        ])

    lines = [f"  WMBTs: {len(resolution.wmbts)} declared by {resolution.feature}"]
    for urn in resolution.wmbts:
        path = resolution.paths.get(urn)
        suffix = f"  ({path})" if path is not None else ""
        lines.append(f"    - {urn}{suffix}")
    lines.extend(_tree_qualifier(resolution.tree))
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

    "Already bound" means RESOLVABLE, not merely truthy (#1689). The skip guard
    used to be ``if data.get("feature")``, which treats a stored ``"TBD"`` as a
    binding and protects it from the repair it needs — the very defect this
    backfill exists to remove, preserved by the check meant to be conservative.
    A stored value that does not resolve in ``plan/`` is not a binding; it is the
    absence of one wearing a value. Where the body declares a URN that DOES
    resolve, such a row is repaired; where it does not, the row is reported as
    ``unrepairable`` rather than silently counted as bound.

    Idempotent: a work item whose stored feature resolves is never overwritten,
    and a repaired row resolves, so a second run writes nothing and reports the
    same sets.
    """
    from atdd.state.work_item_writer import revise_work_item_issue

    store = _open_store(control_root)
    written: List[int] = []
    unresolved: List[int] = []
    unrepairable: List[int] = []

    for ref in _issue_refs(store):
        obj = store.objects.get(ref.object_uid)
        if obj is None:
            continue
        data: Dict[str, Any] = obj.data or {}
        issue_number = int(ref.ref_value)

        stored = data.get("feature")
        if stored and resolve_feature(stored, control_root).resolved:
            continue  # a real, resolvable binding — never overwrite

        candidate = feature_in_body(data.get("body"))
        if candidate is None or not resolve_feature(candidate, control_root).resolved:
            # Distinguish "no binding at all" from "a binding that leads nowhere".
            # Collapsing the two is what let the broken ones hide.
            (unrepairable if stored else unresolved).append(issue_number)
            continue

        if not dry_run:
            revise_work_item_issue(store.conn, issue_number, feature=candidate)
        written.append(issue_number)

    return BackfillReport(
        written=tuple(sorted(written)),
        unresolved=tuple(sorted(unresolved)),
        unrepairable=tuple(sorted(unrepairable)),
    )


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
