"""Wave planning + worktree primitives for `atdd coach`.

These are the dependency-DAG planning and worktree-management helpers that
the durable coach (`atdd coach <issue-numbers...>`) and the two-phase-commit
handler use to fan a multi-issue run out into ordered waves:

    PlannedIssue          — per-issue plan record (number, branch, deps, wave)
    build_plan()          — fetch issue bodies → PlannedIssue map (graph-aware)
    compute_waves()       — topological sort of the dependency DAG into waves
    _branch_to_slug()     — branch → flat directory slug
    _worktree_path_for()  — sibling worktree path for a branch
    _create_worktree()    — `git worktree add` (idempotent)
    _remove_worktree()    — `git worktree remove --force` (best-effort rollback)

Spec references: atdd-coach-spec-v9.md §4.3 (multi-issue orchestration),
§4.7 (PR-based COMPLETE → MERGED two-phase commit).
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from atdd.coach.commands.session_template import (
    IssueContext,
    build_context,
    fetch_issue,
)


@dataclass
class PlannedIssue:
    number: int
    title: str = ""
    body: str = ""
    dependencies: list[int] = field(default_factory=list)
    branch: str = ""
    worktree_path: str = ""
    launch_script_path: str = ""
    workspace_ref: str = ""
    wave: int = -1


def compute_waves(issues: dict[int, PlannedIssue]) -> list[list[int]]:
    """Topological sort → list of waves.

    Wave N contains issues whose deps all resolve to waves < N.
    Deps that point to issues not in `issues` are treated as already-resolved
    (assumed to be merged / out of scope).
    """
    resolved: set[int] = set()
    waves: list[list[int]] = []
    remaining = dict(issues)
    safety = 0
    while remaining:
        safety += 1
        if safety > len(issues) + 2:
            raise ValueError(
                f"Dependency cycle detected among issues: {sorted(remaining)}"
            )
        wave: list[int] = []
        for num, issue in list(remaining.items()):
            deps_in_scope = [d for d in issue.dependencies if d in issues]
            if all(d in resolved for d in deps_in_scope):
                wave.append(num)
        if not wave:
            raise ValueError(
                f"Dependency cycle detected among issues: {sorted(remaining)}"
            )
        for num in wave:
            issues[num].wave = len(waves)
            resolved.add(num)
            del remaining[num]
        waves.append(sorted(wave))
    return waves


def _parse_dep_numbers(body: str) -> list[int]:
    from atdd.coach.commands.session_template import parse_dependencies
    deps = parse_dependencies(body)
    out: list[int] = []
    for d in deps:
        token = d.lstrip("#")
        if token.isdigit():
            out.append(int(token))
    return out


def _branch_to_slug(branch: str) -> str:
    return branch.replace("/", "-") if branch else ""


def _worktree_path_for(branch: str, base: Path) -> Path:
    slug = _branch_to_slug(branch)
    return base.parent / slug


def _create_worktree(branch: str, worktree_path: Path) -> None:
    if worktree_path.exists():
        return
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), branch],
        check=True,
        capture_output=True,
        text=True,
    )


def _remove_worktree(worktree_path: Path) -> None:
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        pass


def build_plan(issue_numbers: list[int]) -> dict[int, PlannedIssue]:
    plan: dict[int, PlannedIssue] = {}
    for num in issue_numbers:
        data = fetch_issue(num)
        if not data:
            print(f"⚠️  could not fetch issue #{num}; skipping", file=sys.stderr)
            continue
        body = data.get("body") or ""
        title = data.get("title") or ""
        context: IssueContext = build_context(num, body, title=title)
        plan[num] = PlannedIssue(
            number=num,
            title=title,
            body=body,
            dependencies=_parse_dep_numbers(body),
            branch=context.branch if context.branch != "TBD" else f"feat/issue-{num}",
        )

    # Graph-aware wave planning (#656): augment the label-derived dependency
    # edges with the wagon consume graph so a downstream-wagon issue is held
    # in a later wave than its upstream sibling, even with no explicit label.
    from atdd.coach.runtime.graph import graph_issue_deps

    graph_deps = graph_issue_deps(list(plan.keys()))
    for num, issue in plan.items():
        for dep in sorted(graph_deps.get(num, set())):
            if dep in plan and dep not in issue.dependencies:
                issue.dependencies.append(dep)

    return plan
