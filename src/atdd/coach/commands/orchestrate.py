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
from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerError,
    get_multiplexer,
)
from atdd.coach.utils.session_naming import (
    branch_to_slug,
    compute_canonical_name,
    compute_repo_short_name,
    target_grid_label,
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
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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


def apply_canonical_name_and_layout(
    backend: MultiplexerBackend,
    ref: str,
    canonical_name: str,
    surface_count: int,
) -> None:
    """Issue #470 dispatch-time pass: rename + announce target layout.

    Two paired application passes:
        1. NAMING — cmux rename-tab + ``/rename`` slash command into the session.
        2. LAYOUT — log the target grid policy for the current surface count.

    Both fail soft (``MultiplexerError`` swallowed) so a missing cmux verb
    or unrenamable backend does not crash the orchestrate flow; babysit's
    drift-detection re-applies on the next tick.
    """
    if not canonical_name:
        return
    try:
        backend.rename(ref, canonical_name)
    except MultiplexerError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        # Best-effort: babysit retries on the next tick.
        pass
    try:
        # Slash-command rename inside the running Claude session so the
        # in-conversation header matches the cmux tab.
        backend.send(ref, f"/rename {canonical_name}\n")
    except MultiplexerError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        pass
    layout = target_grid_label(surface_count)
    print(f"   layout target ({surface_count} surface[s]): {layout}")


def run(
    issue_numbers: list[int],
    autonomous: bool = False,
    resume: bool = False,
    multiplexer: Optional[str] = None,
    multiplexer_mode: str = "workspace",
    dry_run: bool = False,
    state_file: str = ".atdd/orchestrate-state.json",
) -> int:
    if multiplexer_mode not in ("workspace", "pane"):
        print(
            f"❌ unknown --multiplexer-mode '{multiplexer_mode}' "
            f"(expected 'workspace' or 'pane')",
            file=sys.stderr,
        )
        return 5

    state_path = Path(state_file)
    state = load_state(state_path) if resume else {}

    plan = build_plan(issue_numbers)
    if not plan:
        print("❌ no issues could be fetched", file=sys.stderr)
        return 1

    try:
        waves = compute_waves(plan)
    except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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
    except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        print(f"❌ worktree creation failed: {exc.stderr or exc}", file=sys.stderr)
        for wt in created:
            _remove_worktree(wt)
        return 3

    # Phase B: launch scripts + sessions
    try:
        backend: MultiplexerBackend = get_multiplexer(preferred=multiplexer)
    except MultiplexerError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        print(f"❌ {exc}", file=sys.stderr)
        return 4

    # Issue #470: resolve <REPO> short-name once for the whole run.
    repo_short = compute_repo_short_name(load_atdd_config(repo_root))
    launched_count = 0

    for num, issue in plan.items():
        key = str(num)
        if resume and state.get(key, {}).get("launched"):
            issue.workspace_ref = state[key].get("ref") or state[key].get("workspace_ref", "")
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
        # Issue #470: derive the canonical session name from <REPO><N>-<slug>.
        slug = branch_to_slug(issue.branch) or f"issue-{num}"
        canonical_name = compute_canonical_name(repo_short, num, slug)

        try:
            if multiplexer_mode == "pane":
                # Right-anchored grid layout: new surfaces open to the right
                # of the operator's shell pane. The backend's noop default
                # for legacy cmux builds keeps this safe.
                ref = backend.new_surface(
                    cwd=issue.worktree_path,
                    command=launch_cmd,
                    name=canonical_name,
                    direction="right",
                )
            else:
                ref = backend.new_workspace(
                    cwd=issue.worktree_path,
                    command=launch_cmd,
                    name=canonical_name,
                )
        except (MultiplexerError, NotImplementedError) as exc:
            print(f"⚠️  failed to launch session for #{num}: {exc}", file=sys.stderr)
            state[key]["launched"] = False
            save_state(state_path, state)
            continue
        issue.workspace_ref = ref
        state[key].update({
            "launched": True,
            "ref": ref,
            "mode": multiplexer_mode,
            "canonical_name": canonical_name,
        })
        save_state(state_path, state)
        print(f"✓ launched #{num} in {ref} as {canonical_name}")

        launched_count += 1
        apply_canonical_name_and_layout(
            backend=backend,
            ref=ref,
            canonical_name=canonical_name,
            surface_count=launched_count,
        )

    print(
        f"\nOrchestration complete. "
        f"Run `atdd babysit --interval 60` to monitor sessions."
    )
    return 0
