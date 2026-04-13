"""
`atdd orchestrate` — parallel agent session launcher.

Read issue bodies, compute a dependency DAG, topologically sort into waves,
create worktrees, generate launch scripts, and launch multiplexer sessions.

Two-phase commit:
    Phase A — create all worktrees (rollback on failure)
    Phase B — launch sessions (tracked in state file for --resume)

SPEC IDs: SPEC-COACH-ORCH-0001, SPEC-COACH-ORCH-0002, SPEC-COACH-ORCH-0009
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from atdd.coach.commands.session_template import (
    IssueContext,
    build_context,
    fetch_issue,
    render,
)
from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerError,
    get_multiplexer,
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


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


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
    except Exception:
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
    return plan


def print_plan(waves: list[list[int]], plan: dict[int, PlannedIssue]) -> None:
    print(f"Orchestration plan: {len(waves)} wave(s), {len(plan)} issue(s)")
    for i, wave in enumerate(waves):
        print(f"  Wave {i}:")
        for num in wave:
            issue = plan[num]
            deps = ",".join(f"#{d}" for d in issue.dependencies) or "-"
            print(f"    #{num:<5} {issue.branch:<40} deps={deps}")


def run(
    issue_numbers: list[int],
    autonomous: bool = False,
    resume: bool = False,
    multiplexer: Optional[str] = None,
    dry_run: bool = False,
    state_file: str = ".atdd/orchestrate-state.json",
) -> int:
    state_path = Path(state_file)
    state = load_state(state_path) if resume else {}

    plan = build_plan(issue_numbers)
    if not plan:
        print("❌ no issues could be fetched", file=sys.stderr)
        return 1

    try:
        waves = compute_waves(plan)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    print_plan(waves, plan)
    if dry_run:
        return 0

    repo_root = Path.cwd()

    # Phase A: worktrees
    created: list[Path] = []
    try:
        for num, issue in plan.items():
            issue.worktree_path = str(_worktree_path_for(issue.branch, repo_root))
            wt = Path(issue.worktree_path)
            key = str(num)
            if resume and state.get(key, {}).get("worktree_created"):
                continue
            _create_worktree(issue.branch, wt)
            created.append(wt)
            state.setdefault(key, {})["worktree_created"] = True
            state[key]["worktree_path"] = issue.worktree_path
            save_state(state_path, state)
    except subprocess.CalledProcessError as exc:
        print(f"❌ worktree creation failed: {exc.stderr or exc}", file=sys.stderr)
        for wt in created:
            _remove_worktree(wt)
        return 3

    # Phase B: launch scripts + sessions
    try:
        backend: MultiplexerBackend = get_multiplexer(preferred=multiplexer)
    except MultiplexerError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 4

    for num, issue in plan.items():
        key = str(num)
        if resume and state.get(key, {}).get("launched"):
            continue
        context = build_context(
            issue_number=num,
            body=issue.body,
            title=issue.title,
            worktree_path=issue.worktree_path,
        )
        if autonomous:
            context.stop_condition = (
                "Autonomous mode — proceed through REFACTOR without pausing "
                "for user confirmation."
            )
        script = render(context)
        script_path = Path(issue.worktree_path) / ".launch_prompt.txt"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script)
        issue.launch_script_path = str(script_path)

        launch_cmd = (
            "claude --dangerously-skip-permissions "
            f"\"$(cat {script_path})\""
        )
        try:
            ref = backend.new_workspace(
                cwd=issue.worktree_path,
                command=launch_cmd,
                name=f"issue-{num}",
            )
        except MultiplexerError as exc:
            print(f"⚠️  failed to launch session for #{num}: {exc}", file=sys.stderr)
            state[key]["launched"] = False
            save_state(state_path, state)
            continue
        issue.workspace_ref = ref
        state[key].update({"launched": True, "workspace_ref": ref})
        save_state(state_path, state)
        print(f"✓ launched #{num} in {ref}")

    print(
        f"\nOrchestration complete. "
        f"Run `atdd babysit --interval 60` to monitor sessions."
    )
    return 0
