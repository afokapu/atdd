"""Two-phase-commit for the durable coach per spec §4.6.

J4 (issue #502) owns the coach-side Phase A / Phase B loops. The worktree
primitives ``_create_worktree`` and ``_remove_worktree`` live in
``commands/wave_planning.py``; this module imports them and owns the new
rollback-disciplined loops.

Phase A — worktree creation
    Iterates over the plan and calls ``_create_worktree`` for each
    issue. Successful creations are appended to ``decisions.jsonl`` as
    ``worktree-create`` records (a successful idempotency probe on
    resume short-circuits the call). On any failure, every
    already-created worktree is removed via ``_remove_worktree`` and
    the matching durable decisions are reverted out of the
    in-memory tracking. The decisions corresponding to rolled-back
    creations are NOT written: durability follows action, not intent.

Phase B — session launch
    Renders launch prompts and dispatches via the multiplexer. Each
    successful launch writes an ``agent-spawn`` decision to
    ``decisions.jsonl``. Failed launches are logged but do NOT roll
    back already-launched siblings — a launched agent has spawned a
    process and may be doing work; the resume runner picks up the
    un-launched siblings on a subsequent run.

Resume source
    ``decisions.jsonl`` is the durable resume source. This module never
    writes a legacy state file. ``--resume`` reconstruction itself is
    owned by #J6.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from atdd.coach.commands.durability import DecisionWriter
from atdd.coach.commands.wave_planning import (
    PlannedIssue,
    _branch_to_slug,
    _create_worktree,
    _remove_worktree,
    _worktree_path_for,
)
from atdd.coach.commands.session_template import build_context, render
from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.multiplexer import (
    MultiplexerBackend,
    MultiplexerError,
)
from atdd.coach.utils.session_naming import (
    branch_to_slug,
    compute_canonical_name,
    compute_repo_short_name,
)


# Indirections that tests can monkeypatch without touching orchestrate.py
# directly. The default callables delegate to the absorbed helpers.
def _create_worktree_call(branch: str, worktree_path: Path, *, _issue_number: int) -> None:
    _create_worktree(branch, worktree_path)


def _remove_worktree_call(worktree_path: Path) -> None:
    _remove_worktree(worktree_path)


@dataclass
class PhaseAResult:
    """Outcome of Phase A.

    ``failed_issue`` is set to the issue number whose worktree creation
    raised; on success it is ``None``. ``created_paths`` lists the
    worktree paths actually created in this invocation (excluding
    idempotent skips).
    """

    failed_issue: Optional[int] = None
    failed_error: Optional[str] = None
    created_paths: list[Path] = field(default_factory=list)
    rolled_back_paths: list[Path] = field(default_factory=list)


@dataclass
class PhaseBResult:
    """Outcome of Phase B.

    ``launched_issues`` is the issue numbers for which an agent-spawn
    decision was durably recorded. ``failed_issues`` is those whose
    launch raised; failures do NOT trigger rollback of siblings.
    """

    launched_issues: list[int] = field(default_factory=list)
    failed_issues: list[int] = field(default_factory=list)
    refs: dict[int, str] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _worktree_decision_id(run_id: str, issue_number: int) -> str:
    return f"{run_id}:#{issue_number}:worktree-create"


def _spawn_decision_id(run_id: str, issue_number: int) -> str:
    return f"{run_id}:#{issue_number}:agent-spawn"


def phase_a_create_worktrees(
    plan: dict[int, PlannedIssue],
    repo_root: Path,
    decision_writer: DecisionWriter,
    run_id: str,
) -> PhaseAResult:
    """Create one worktree per planned issue with rollback-on-any-failure.

    Per spec §4.6 the rollback discipline is verbatim from orchestrate:
    if any creation fails, every already-created worktree is removed
    before the function returns. The matching durable decisions are
    only appended for creations that ultimately persist.
    """
    result = PhaseAResult()
    created: list[Path] = []
    pending_decisions: list[dict] = []

    for num, issue in plan.items():
        worktree_path = _worktree_path_for(issue.branch, repo_root)
        issue.worktree_path = str(worktree_path)
        decision_id = _worktree_decision_id(run_id, num)

        # Idempotent skip: if this run already recorded creation for
        # this issue, the helper itself is also a no-op (the worktree
        # exists), and we do not append a duplicate decision.
        if decision_writer.has_decision(decision_id):
            continue

        try:
            _create_worktree_call(issue.branch, worktree_path, _issue_number=num)
        except subprocess.CalledProcessError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            err = (exc.stderr or "").strip() or str(exc)
            print(
                f"❌ worktree creation failed for #{num}: {err}",
                file=sys.stderr,
            )
            result.failed_issue = num
            result.failed_error = err
            for path in reversed(created):
                _remove_worktree_call(path)
                result.rolled_back_paths.append(path)
            return result
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            err = str(exc)
            print(
                f"❌ worktree creation failed for #{num}: {err}",
                file=sys.stderr,
            )
            result.failed_issue = num
            result.failed_error = err
            for path in reversed(created):
                _remove_worktree_call(path)
                result.rolled_back_paths.append(path)
            return result

        created.append(worktree_path)
        pending_decisions.append({
            "decision_id": decision_id,
            "timestamp": _now(),
            "coach_run_id": run_id,
            "issue_number": num,
            "decision_type": "worktree-create",
            "inputs": {
                "branch": issue.branch,
                "worktree_path": str(worktree_path),
            },
            "outcome": {
                "created": True,
                "worktree_path": str(worktree_path),
            },
        })

    # Phase A succeeded: durably record every creation. Decisions are
    # only written after the whole loop succeeds so a mid-loop failure
    # leaves zero ``worktree-create`` records on disk for this run.
    for record in pending_decisions:
        decision_writer.append(record)

    result.created_paths = created
    return result


def phase_b_launch_sessions(
    plan: dict[int, PlannedIssue],
    repo_root: Path,
    backend: MultiplexerBackend,
    decision_writer: DecisionWriter,
    run_id: str,
    *,
    multiplexer_mode: str = "surface",
    autonomous: bool = False,
) -> PhaseBResult:
    """Launch one session per issue with asymmetric rollback semantics.

    Per spec §4.6: failed launches are logged but already-launched
    siblings are NOT rolled back. The successful launches are recorded
    via ``decisions.jsonl`` so ``--resume`` can pick up the un-launched
    siblings.
    """
    result = PhaseBResult()
    repo_short = compute_repo_short_name(load_atdd_config(repo_root))

    for num, issue in plan.items():
        decision_id = _spawn_decision_id(run_id, num)
        if decision_writer.has_decision(decision_id):
            continue

        worktree_path = Path(issue.worktree_path) if issue.worktree_path else None
        if worktree_path is None or not worktree_path.exists():
            print(
                f"⚠️  Phase B: missing worktree for #{num}; skipping",
                file=sys.stderr,
            )
            result.failed_issues.append(num)
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
        script_path = worktree_path / ".launch_prompt.txt"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script)
        issue.launch_script_path = str(script_path)

        slug = branch_to_slug(issue.branch) or f"issue-{num}"
        canonical_name = compute_canonical_name(repo_short, num, slug)
        # Bare interactive launch — the prompt is injected post-boot via
        # paste_text + send_key (#702). Claude Code v2.1.x ignores a
        # positional prompt arg in interactive mode, so `$(cat ...)` here
        # silently produced an idle session with no task.
        #
        # #971: the leash is retired here too — the surfacing flags come from the
        # same DecisionSurfacingPolicy the cmd_spawn adapter uses, so this second
        # launch transport never reintroduces the freedom-set bug (Y002). Bash is
        # absent from --allowedTools so it surfaces to the cmux Feed.
        from atdd.coach.commands.spawn import _claude_surfacing_flags

        launch_cmd = f"claude {_claude_surfacing_flags('claude-code')}"

        try:
            pane_ref = backend.resolve_focused_pane() if hasattr(backend, "resolve_focused_pane") else "pane:1"
            ref = backend.new_surface_in_pane(
                pane_ref=pane_ref,
                cwd=str(worktree_path),
                command=launch_cmd,
                name=canonical_name,
            )
        except (MultiplexerError, NotImplementedError) as exc:
            # Asymmetric rollback per spec §4.6: failed launches are
            # logged but already-launched siblings are NOT undone. No
            # ``agent-spawn`` decision is written for the failed launch
            # — a successful spawn is the precondition for recording.
            print(
                f"⚠️  failed to launch session for #{num}: {exc}",
                file=sys.stderr,
            )
            result.failed_issues.append(num)
            continue

        issue.workspace_ref = ref
        result.refs[num] = ref
        result.launched_issues.append(num)

        # Inject the launch prompt post-boot (#702): claude ignores a
        # positional prompt arg in interactive mode. paste_text uses
        # bracketed paste so the multi-line prompt lands as one block;
        # send_key submits it. NOTE: phase_b is not yet wired into a live
        # command path — when it is, add a claude-readiness poll before
        # the paste (unlike cmd_spawn, no /rename injection precedes it
        # here to prove the surface is ready).
        try:
            backend.paste_text(ref, script_path.read_text())
            backend.send_key(ref, "Enter")
        except (MultiplexerError, NotImplementedError, OSError, AttributeError) as exc:
            print(
                f"⚠️  launch-prompt injection failed for #{num}: {exc}",
                file=sys.stderr,
            )

        decision_writer.append({
            "decision_id": decision_id,
            "timestamp": _now(),
            "coach_run_id": run_id,
            "issue_number": num,
            "decision_type": "agent-spawn",
            "inputs": {
                "branch": issue.branch,
                "worktree_path": str(worktree_path),
                "canonical_name": canonical_name,
                "multiplexer_mode": multiplexer_mode,
            },
            "outcome": {
                "launched": True,
                "ref": ref,
                "canonical_name": canonical_name,
            },
        })
        print(f"✓ launched #{num} in {ref} as {canonical_name}")

    return result
