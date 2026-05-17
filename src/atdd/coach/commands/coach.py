"""`atdd coach <issue-numbers...>` — durable orchestrator entry point.

J1 (issue #496) ships ONLY the state-machine skeleton and the §5.1 CLI
argparse surface. Every other coach v9 track (J2/J3/J4/J5/J6 and the
K/L/M/N/O/P tracks) hooks into the symbols this module exposes:

    Phase                 — the per-issue state enum (§4.1)
    TRANSITION_TABLE      — legal transitions between Phases (§4.1)
    can_transition()      — table lookup helper
    StateMachine          — per-issue state container
    initialize_state_machine() — factory that returns a StateMachine in INIT
    Config                — resolved CLI configuration
    Policy                — wave-transition gating policy
    parse_cli()           — argparse over the §5.1 flag surface
    resolve_policy()      — Config → Policy (carries --strict-deps)
    build_plan            — re-export from orchestrate
    compute_waves         — re-export from orchestrate (per §0.2 absorption)
    run()                 — main entry point

Spec references: atdd-coach-spec-v9.md §4.1 (per-issue states),
§4.3 (multi-issue orchestration), §5.1 (CLI), §0.2 (absorption inventory).

Out of scope (each owned by a downstream issue):
- watcher attachment (#J5)
- validator dispatch (#M3)
- observer correction injection (#L1)
- spawn integration / multiplexer (#K1)
- two-phase-commit worktree creation/rollback (#J4)
- decision durability writes (#J3)
- resume reconstruction (#J6)
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_logger = logging.getLogger("atdd.coach")

# Per spec §0.2 absorption discipline: reuse, do not redefine.
# P5 (#531): orchestrate.py archived; import from _archived.
from atdd.coach.commands._archived.orchestrate import build_plan, compute_waves

# State-machine types extracted to handlers package (#591 split).
# Re-exported here so all existing importers continue to work unchanged.
from atdd.coach.handlers.state_machine import (
    Phase,
    PLANNED_PATH,
    StateMachine,
    TRANSITION_TABLE,
    can_transition,
    initialize_state_machine,
)
from atdd.coach.utils.escalation_channel import validate_escalation_channel_arg

__all__ = [
    "Phase",
    "PLANNED_PATH",
    "StateMachine",
    "TRANSITION_TABLE",
    "can_transition",
    "initialize_state_machine",
    "Config",
    "Policy",
    "parse_cli",
    "resolve_policy",
    "build_plan",
    "compute_waves",
    "run",
    "run_cli",
    "run_status",
    "run_review",
    "run_watch",
    "run_gc",
    "resolve_or_create_coach_surface",
    "build_consolidated_view",
    "render_consolidated_view",
    "add_worker_surface",
    "main",
]

# Re-export run_status so test imports from atdd.coach.commands.coach work.
# The implementation lives in coach_status.py to satisfy J1 scope constraints.
from atdd.coach.commands.coach_status import run_status  # noqa: E402

# Re-export run_review so test imports from atdd.coach.commands.coach work.
# The implementation lives in coach_review.py (#624).
from atdd.coach.commands.coach_review import run_review  # noqa: E402

# Re-export run_watch so test imports from atdd.coach.commands.coach work.
# The implementation lives in coach_watch.py (#628).
from atdd.coach.commands.coach_watch import run_watch  # noqa: E402

# Re-export run_gc so test imports from atdd.coach.commands.coach work.
# The implementation lives in coach_gc.py (#655).
from atdd.coach.commands.coach_gc import run_gc  # noqa: E402


# Coach workspace layout — single canonical tab + consolidated view (#736).
# Implementation lives in coach_workspace.py; re-exported here so existing
# importers (`coach.resolve_or_create_coach_surface`, ...) are unaffected.
from atdd.coach.commands.coach_workspace import (  # noqa: E402
    add_worker_surface,
    build_consolidated_view,
    render_consolidated_view,
    resolve_or_create_coach_surface,
)


# ---------------------------------------------------------------------------
# CLI surface (spec §5.1)
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Resolved configuration printable for inspection."""

    issue_numbers: list[int]
    max_retries: Optional[int] = None
    escalation_channel: Optional[str] = None
    multiplexer: Optional[str] = None
    multiplexer_mode: str = "workspace"
    auto_merge: bool = False
    strict_deps: bool = False
    llm: Optional[str] = None
    persona_llm: dict[str, str] = field(default_factory=dict)
    judge_llm: Optional[str] = None
    require_issue_review: str = "warn"
    review_phases: set[str] = field(default_factory=set)
    skip_review: bool = False
    risk_threshold_block: Optional[int] = None
    allow_stale_suppressions: bool = False
    resume: Optional[str] = None
    dry_run: bool = False
    stale_warn_minutes: Optional[int] = None


@dataclass
class Policy:
    """Wave-transition gating policy derived from Config.

    J1 just carries `strict_deps` forward; downstream tracks consult it
    to decide whether a wave is allowed to advance with unresolved deps.
    """

    strict_deps: bool


@dataclass
class ColdStartResult:
    """Aggregate outcome of a cold-start run (issue #730).

    ``rc`` is the process exit code — 0 when every issue reached a terminal
    success state, the first non-zero member ``rc`` otherwise. ``blocked``
    lists the issue numbers that resolved to BLOCKED, so the operator can see
    which member stalled without that member aborting its siblings.
    """

    rc: int
    blocked: list[int] = field(default_factory=list)


def _persona_llm_arg(value: str) -> dict[str, str]:
    """Parse `--persona-llm tester=a,coder=b,reviewer=c` into a dict."""
    out: dict[str, str] = {}
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise argparse.ArgumentTypeError(
                f"--persona-llm token {token!r} must be persona=model"
            )
        persona, model = token.split("=", 1)
        persona = persona.strip()
        model = model.strip()
        if not persona or not model:
            raise argparse.ArgumentTypeError(
                f"--persona-llm token {token!r} must be persona=model"
            )
        out[persona] = model
    return out


def _review_phases_arg(value: str) -> set[str]:
    """Parse `--review-phases planned,red,green` into a set."""
    return {p.strip() for p in value.split(",") if p.strip()}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach",
        description=(
            "Durable per-issue orchestrator (coach v9). J1 skeleton: state "
            "machine + CLI surface only; watchers/validators/observers/spawn "
            "live in adjacent tracks."
        ),
    )
    parser.add_argument(
        "issue_numbers",
        type=int,
        nargs="+",
        help="GitHub issue numbers to coach.",
    )
    parser.add_argument("--max-retries", type=int, default=None, dest="max_retries")
    parser.add_argument(
        "--escalation-channel",
        type=validate_escalation_channel_arg,
        default=None,
        dest="escalation_channel",
        help=(
            "Where to route escalations. Forms: file:<path>, <path>, "
            "slack-webhook:<https-url>, gh-issue:owner/repo#N, gh-issue:#N."
        ),
    )
    parser.add_argument(
        "--multiplexer",
        type=str,
        choices=["cmux", "zellij", "tmux"],
        default=None,
    )
    parser.add_argument(
        "--multiplexer-mode",
        type=str,
        choices=["workspace", "pane"],
        default="workspace",
        dest="multiplexer_mode",
    )
    parser.add_argument(
        "--auto-merge", action="store_true", dest="auto_merge",
    )
    parser.add_argument(
        "--strict-deps", action="store_true", dest="strict_deps",
    )
    parser.add_argument("--llm", type=str, default=None)
    parser.add_argument(
        "--persona-llm",
        type=_persona_llm_arg,
        default={},
        dest="persona_llm",
        help="tester=MODEL,coder=MODEL,reviewer=MODEL",
    )
    parser.add_argument("--judge-llm", type=str, default=None, dest="judge_llm")
    parser.add_argument(
        "--require-issue-review",
        type=str,
        choices=["warn", "block", "auto"],
        default="warn",
        dest="require_issue_review",
    )
    parser.add_argument(
        "--review-phases",
        type=_review_phases_arg,
        default=set(),
        dest="review_phases",
    )
    parser.add_argument(
        "--skip-review", action="store_true", dest="skip_review",
    )
    parser.add_argument(
        "--risk-threshold-block",
        type=int,
        default=None,
        dest="risk_threshold_block",
    )
    parser.add_argument(
        "--allow-stale-suppressions",
        action="store_true",
        dest="allow_stale_suppressions",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="Carried for #J6 resume runner; J1 parses but does not reconstruct.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
    )
    parser.add_argument(
        "--stale-warn",
        type=int,
        default=None,
        dest="stale_warn_minutes",
        metavar="MINUTES",
        help="Emit INFO escalation after MINUTES of no watcher events.",
    )
    return parser


def parse_cli(argv: list[str]) -> Config:
    ns = _build_parser().parse_args(argv)
    return Config(
        issue_numbers=ns.issue_numbers,
        max_retries=ns.max_retries,
        escalation_channel=ns.escalation_channel,
        multiplexer=ns.multiplexer,
        multiplexer_mode=ns.multiplexer_mode,
        auto_merge=ns.auto_merge,
        strict_deps=ns.strict_deps,
        llm=ns.llm,
        persona_llm=ns.persona_llm,
        judge_llm=ns.judge_llm,
        require_issue_review=ns.require_issue_review,
        review_phases=ns.review_phases,
        skip_review=ns.skip_review,
        risk_threshold_block=ns.risk_threshold_block,
        allow_stale_suppressions=ns.allow_stale_suppressions,
        resume=ns.resume,
        dry_run=ns.dry_run,
        stale_warn_minutes=ns.stale_warn_minutes,
    )


def resolve_policy(cfg: Config) -> Policy:
    return Policy(strict_deps=cfg.strict_deps)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _print_planned_path(sm: StateMachine) -> None:
    arrow = " → ".join(p.value for p in PLANNED_PATH)
    print(f"  #{sm.issue_number}: {sm.phase.value} ({arrow})")


# ---------------------------------------------------------------------------
# Cold-start advance map (issue #645 — extends watcher._ADVANCE_FROM to
# include the PLANNED→RED transition driven by the planner's commit).
# ---------------------------------------------------------------------------

_COLD_START_ADVANCE_FROM: dict[Phase, Phase] = {
    Phase.PLANNED: Phase.RED,
    Phase.RED: Phase.GREEN,
    Phase.GREEN: Phase.SMOKE,
    Phase.SMOKE: Phase.REFACTOR,
    Phase.REFACTOR: Phase.COMPLETE,
}

_PHASE_TRAILER_MAP: dict[str, Phase] = {
    "INIT": Phase.INIT,
    "PLANNED": Phase.PLANNED,
    "RED": Phase.RED,
    "GREEN": Phase.GREEN,
    "SMOKE": Phase.SMOKE,
    "REFACTOR": Phase.REFACTOR,
    "COMPLETE": Phase.COMPLETE,
}


def _cold_start_proposed_transition(sm: StateMachine, event: dict) -> Optional["Transition"]:
    """Map a raw queue event to a (src, dst) Transition per cold-start rules.

    Two triggers advance the cold-start loop:

    * ``agent_done`` (#708) — a dispatched persona wrote ``done.json``,
      signalling its phase is complete. The event's ``agent_id`` encodes
      the issue (``<persona>-<issue>-<suffix>``); the SM's current phase
      determines the next via ``_COLD_START_ADVANCE_FROM``. This is the
      primary cold-start trigger — it needs no commit trailers and no
      separate git_watcher process.
    * ``commit_observed`` — a commit carrying ``Issue``/``Phase`` trailers
      (the original J5 path; retained for the trailer-driven flow).

    Extends the J5 watcher map to include PLANNED→RED so the cold-start
    event loop handles the full lifecycle (issue #645 / #708).
    """
    from atdd.coach.handlers.state_machine import Transition, can_transition

    event_type = event.get("event_type")

    # #708 — persona done-signal: advance one phase from the SM's current
    # phase. The agent_id form is ``<persona>-<issue>-<suffix>`` (the
    # observer's ``…-observer`` agent never writes done.json, so only a
    # real persona triggers this).
    if event_type == "agent_done":
        agent_id = event.get("agent_id") or ""
        parts = agent_id.split("-")
        if len(parts) < 2 or not parts[1].isdigit():
            return None
        if str(sm.issue_number) != parts[1]:
            return None
        dst = _COLD_START_ADVANCE_FROM.get(sm.phase)
        if dst is None or not can_transition(sm.phase, dst):
            return None
        return Transition(sm.phase, dst)

    if event_type != "commit_observed":
        return None
    payload = event.get("payload") or {}
    trailers = payload.get("trailers") or {}
    issue_str = trailers.get("Issue")
    if issue_str is None or str(sm.issue_number) != str(issue_str):
        return None
    phase_str = trailers.get("Phase")
    if not phase_str:
        return None
    completed = _PHASE_TRAILER_MAP.get(phase_str)
    if completed is None or completed != sm.phase:
        return None
    dst = _COLD_START_ADVANCE_FROM.get(completed)
    if dst is None:
        return None
    if not can_transition(sm.phase, dst):
        return None
    return Transition(sm.phase, dst)


def _write_escalation(escalation_channel: Optional[str], message: str) -> None:
    """Append an escalation message to the configured channel (R5, issue #645)."""
    if not escalation_channel:
        print(f"[coach:escalation] {message}", file=sys.stderr)
        return
    raw = escalation_channel.strip()
    path_str = raw[len("file:"):] if raw.startswith("file:") else raw
    if ":" not in path_str or path_str.startswith((".", "/", "~")):
        try:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            with p.open("a", encoding="utf-8") as fh:
                fh.write(f"{now} {message}\n")
        except OSError as exc:
            print(f"[coach:escalation] write failed ({exc}): {message}", file=sys.stderr)
    else:
        print(f"[coach:escalation] {message}", file=sys.stderr)


def _try_emit_telemetry(issue: int, from_phase: Phase, to_phase: Phase) -> None:
    """Best-effort telemetry emit (R7, issue #645). Skip if module absent."""
    try:
        from atdd.coach.telemetry import emit_phase_transition  # type: ignore[import]
        emit_phase_transition(issue, from_phase, to_phase)
    except (ImportError, Exception):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-01
        pass


def _make_phase_transition_record(
    coach_run_id: str,
    issue_number: int,
    src: Phase,
    dst: Phase,
) -> dict:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "decision_id": f"{coach_run_id}:#{issue_number}:{src.value}->{dst.value}",
        "timestamp": now,
        "coach_run_id": coach_run_id,
        "issue_number": issue_number,
        "decision_type": "phase-transition",
        "inputs": {"current_phase": src.value, "target_phase": dst.value},
        "outcome": {"transitioned": True, "new_phase": dst.value},
    }


def _ensure_issue_worktree(ctx) -> Optional[Path]:
    """Cold-start: ensure the issue's git worktree exists, creating it if absent.

    The spawn handler's ``_resolve_worktree`` only *derives* a path — it never
    runs ``git worktree add``. ``phase_a_create_worktrees`` was written but
    never wired into a live command path. Without this step the planner is
    dispatched into a bare non-git directory and its commits land on protected
    ``main`` (2026-05-16 incident).

    The worktree path is taken from the spawn handler's ``_resolve_worktree``
    so creation and dispatch always agree. The branch is read from the issue
    body's ``Branch:`` metadata, falling back to ``feat/issue-<N>``.

    Idempotent: an existing git worktree is returned unchanged. Returns the
    worktree ``Path``, or ``None`` if creation failed (caller → BLOCKED).
    """
    from atdd.coach.commands import session_template
    from atdd.coach.handlers.spawn import _resolve_worktree

    worktree = _resolve_worktree(ctx)

    # Idempotent: an existing git worktree is reused unchanged.
    if (worktree / ".git").exists():
        return worktree

    # The real `_resolve_worktree` always returns a direct sibling of the
    # repo root (`Path.cwd().parent / <slug>`). A resolved path that is NOT
    # such a sibling means `_resolve_worktree` was injected (tests) or the
    # layout is non-standard — running `git worktree add` there would be
    # wrong, so the path is taken as-is and no worktree is created.
    repo_root = Path.cwd()
    if worktree.parent != repo_root.parent:
        return worktree

    fetched = session_template.fetch_issue(ctx.issue_number) or {}
    meta = session_template.parse_metadata(fetched.get("body") or "")
    branch = (meta.get("Branch") or "").strip()
    if not branch or branch == "TBD":
        branch = f"feat/issue-{ctx.issue_number}"

    # A path that exists but is not a git worktree needs triage before
    # `git worktree add` (which accepts only a missing or empty directory):
    #  - empty            → fine, git accepts it as-is.
    #  - atdd-only residue → stale debris from the pre-fix bug; safe to clear.
    #  - anything else     → hard failure, never silently clobbered.
    if worktree.exists():
        entries = {p.name for p in worktree.iterdir()}
        if not entries:
            pass  # empty dir — git worktree add accepts it
        elif entries <= {".atdd", ".launch_prompt.txt", ".DS_Store"}:
            shutil.rmtree(worktree)
        else:
            print(
                f"❌ #{ctx.issue_number}: worktree path {worktree} exists and is "
                f"not a git worktree; refusing to overwrite",
                file=sys.stderr,
            )
            return None

    # Attach to an existing remote branch if present, else create a new one.
    remote = subprocess.run(
        ["git", "branch", "-r", "--list", f"origin/{branch}"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if remote.stdout.strip():
        add_cmd = ["git", "worktree", "add", str(worktree), f"origin/{branch}"]
    else:
        add_cmd = ["git", "worktree", "add", str(worktree), "-b", branch]

    result = subprocess.run(
        add_cmd, cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(
            f"❌ #{ctx.issue_number}: git worktree add failed: "
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        return None

    _logger.info(
        "coach cold-start worktree created",
        extra={
            "issue": ctx.issue_number,
            "worktree": str(worktree),
            "branch": branch,
        },
    )
    return worktree


def _drive_single_issue(
    cfg: "Config",
    sm: StateMachine,
    runtime_dir: Path,
    *,
    _spawn_func: Optional[Callable] = None,
    _two_phase_func: Optional[Callable] = None,
    _injected_events: Optional[list] = None,
    _max_loop_events: Optional[int] = None,
    _run_id_sink: Optional[list] = None,
) -> int:
    """Drive one issue from INIT through the full lifecycle.

    Returns 0 on COMPLETE (or REFACTOR halt without --auto-merge),
    1 on BLOCKED/spawn-failure, 2 on unrecoverable error.
    Issue #645 — cold-start wiring.
    """
    from atdd.coach.handlers import spawn as spawn_handler, two_phase_commit as tpc_handler
    from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition
    from atdd.coach.commands.durability import DecisionWriter, transactional_decision

    spawn_h = _spawn_func or spawn_handler.handle
    two_phase_h = _two_phase_func or tpc_handler.handle

    coach_run_id = f"coach-run-{sm.issue_number}-{uuid.uuid4().hex[:8]}"
    if _run_id_sink is not None:
        _run_id_sink.append(coach_run_id)

    ctx = CoachContext(
        issue_number=sm.issue_number,
        coach_run_id=coach_run_id,
        runtime_dir=runtime_dir,
        dry_run=cfg.dry_run,
        multiplexer=cfg.multiplexer,
        multiplexer_mode=cfg.multiplexer_mode,
        llm=cfg.llm,
        persona_llm=cfg.persona_llm,
        judge_llm=cfg.judge_llm,
        require_issue_review=cfg.require_issue_review,
        review_phases=cfg.review_phases,
        skip_review=cfg.skip_review,
        risk_threshold_block=cfg.risk_threshold_block,
        allow_stale_suppressions=cfg.allow_stale_suppressions,
        auto_merge=cfg.auto_merge,
        max_retries=cfg.max_retries,
        escalation_channel=cfg.escalation_channel,
    )

    writer = DecisionWriter(runtime_dir=runtime_dir)

    # --- Step 1: Write INIT→PLANNED decision (durability before action, R4) ---
    init_record = _make_phase_transition_record(coach_run_id, sm.issue_number, Phase.INIT, Phase.PLANNED)
    with transactional_decision(writer, init_record):
        pass  # decision is written by the CM; no blocking action here

    # --- Step 1.5: Ensure the issue's git worktree exists (cold-start) ---
    # The spawn handler resolves a worktree *path* but never creates the
    # worktree. Without this, the planner is dispatched into a bare non-git
    # directory and its commits land on protected `main` (2026-05-16 incident).
    if not cfg.dry_run:
        worktree = _ensure_issue_worktree(ctx)
        if worktree is None:
            _logger.error(
                "coach cold-start worktree creation failed",
                extra={"issue": sm.issue_number, "phase": "INIT→PLANNED", "trigger": "cold-start"},
            )
            _write_escalation(
                cfg.escalation_channel,
                f"#{sm.issue_number}: worktree creation failed at INIT→PLANNED",
            )
            sm.history.append(sm.phase)
            sm.phase = Phase.BLOCKED
            return 1

    # --- Step 2: Spawn planner (K1) ---
    spawn_result = spawn_h(ctx, Transition(Phase.INIT, Phase.PLANNED))
    if spawn_result == HandlerResult.ERROR:
        _logger.error(
            "coach cold-start spawn failed",
            extra={"issue": sm.issue_number, "phase": "INIT→PLANNED", "trigger": "cold-start"},
        )
        _write_escalation(cfg.escalation_channel, f"#{sm.issue_number}: spawn failed at INIT→PLANNED")
        sm.history.append(sm.phase)
        sm.phase = Phase.BLOCKED
        return 1

    # --- Step 3: Advance SM INIT → PLANNED ---
    sm.history.append(sm.phase)
    sm.phase = Phase.PLANNED
    _logger.info(
        "coach cold-start advance",
        extra={"issue": sm.issue_number, "phase": "INIT→PLANNED", "trigger": "cold-start"},
    )
    _try_emit_telemetry(sm.issue_number, Phase.INIT, Phase.PLANNED)

    # --- Step 4: Event-driven loop ---
    if _injected_events is not None:
        _process_injected_events(ctx, sm, _injected_events, writer, spawn_h)
    elif _max_loop_events == 0:
        pass  # test seam: skip event loop entirely
    else:
        _process_watcher_events(ctx, sm, runtime_dir, cfg, writer, spawn_h,
                                max_events=_max_loop_events)

    # --- Step 5: Handle terminal states ---
    if sm.phase == Phase.BLOCKED:
        return 1

    if sm.phase == Phase.REFACTOR and not cfg.auto_merge:
        # R5: stop at REFACTOR when auto-merge is off; escalate for operator review
        msg = (
            f"#{sm.issue_number} reached REFACTOR. "
            f"Run: atdd coach {sm.issue_number} --auto-merge to proceed."
        )
        _write_escalation(cfg.escalation_channel, msg)
        _logger.info(
            "coach REFACTOR escalated",
            extra={"issue": sm.issue_number, "phase": "REFACTOR", "trigger": "escalate-no-auto-merge"},
        )
        return 0

    if sm.phase == Phase.COMPLETE:
        t_complete = Transition(Phase.COMPLETE, Phase.MERGED)
        result = two_phase_h(ctx, t_complete)
        if result == HandlerResult.HANDLED:
            sm.history.append(sm.phase)
            sm.phase = Phase.MERGED
            _logger.info(
                "coach auto-merge advance",
                extra={"issue": sm.issue_number, "phase": "COMPLETE→MERGED", "trigger": "auto-merge"},
            )
            _try_emit_telemetry(sm.issue_number, Phase.COMPLETE, Phase.MERGED)
        elif result == HandlerResult.ERROR:
            _write_escalation(cfg.escalation_channel, f"#{sm.issue_number}: two-phase commit failed")
            return 1
        # NOOP → no auto-merge; COMPLETE persists pending operator action

    return 0


def _process_injected_events(
    ctx: "CoachContext",
    sm: StateMachine,
    events: list,
    writer: "DecisionWriter",
    spawn_h: Callable,
) -> None:
    """Process a pre-programmed event list (test seam for cold-start, issue #645)."""
    from atdd.coach.handlers.state_machine import HandlerResult, Transition
    from atdd.coach.commands.durability import transactional_decision

    for event in events:
        if sm.phase in (Phase.COMPLETE, Phase.MERGED, Phase.BLOCKED):
            break
        t = _cold_start_proposed_transition(sm, event)
        if t is None:
            continue
        record = _make_phase_transition_record(
            ctx.coach_run_id, ctx.issue_number, t.src, t.dst
        )
        with transactional_decision(writer, record):
            pass
        sm.history.append(sm.phase)
        sm.phase = t.dst
        _logger.info(
            "coach injected event advance",
            extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}",
                   "trigger": event.get("event_type", "injected")},
        )
        _try_emit_telemetry(ctx.issue_number, t.src, t.dst)
        # Spawn next persona for this transition
        spawn_result = spawn_h(ctx, t)
        if spawn_result == HandlerResult.ERROR:
            _logger.error(
                "coach injected event spawn failed",
                extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}"},
            )
            sm.history.append(sm.phase)
            sm.phase = Phase.BLOCKED
            break


def _watcher_runtime_dir(ctx: "CoachContext", fallback: Path) -> Path:
    """Runtime dir the coach's ``RuntimeWatcher`` must scan (#708 link 3).

    A dispatched persona runs *inside the issue's worktree* and writes its
    runtime artifacts (``events.jsonl``, ``done.json``, …) to
    ``<worktree>/.atdd/runtime`` — NOT the coach process's cwd runtime. If
    the watcher scans the coach's cwd it never sees a persona event and the
    coach never advances past the first phase. Resolve the issue's worktree
    and point the watcher at its ``.atdd/runtime``; fall back to
    ``fallback`` only when the worktree cannot be resolved.
    """
    try:
        from atdd.coach.handlers.spawn import _resolve_worktree

        worktree = _resolve_worktree(ctx)
    except Exception as exc:  # noqa: BLE001 — best-effort; logged, then fall back
        _logger.warning(
            "coach watcher: worktree resolution failed; using fallback runtime dir",
            extra={"issue": getattr(ctx, "issue_number", "?"), "error": str(exc)},
        )
        return fallback
    return worktree / ".atdd" / "runtime"


def _process_watcher_events(
    ctx: "CoachContext",
    sm: StateMachine,
    runtime_dir: Path,
    cfg: "Config",
    writer: "DecisionWriter",
    spawn_h: Callable,
    *,
    max_events: Optional[int] = None,
) -> None:
    """Block on WatcherEventLoop until SM reaches a terminal state (production path)."""
    from atdd.coach.commands.event_queue import CoachEventQueue
    from atdd.coach.commands.runtime_watcher import RuntimeWatcher
    from atdd.coach.handlers.state_machine import HandlerResult, Transition
    from atdd.coach.commands.durability import transactional_decision

    # #708 link 3: the watcher must scan the dispatched persona's worktree
    # runtime, not the coach cwd's. The CoachEventQueue stays on the coach's
    # own runtime_dir (coach-side durability) — only the watcher's scan root
    # follows the persona.
    watch_runtime = _watcher_runtime_dir(ctx, runtime_dir)
    queue = CoachEventQueue(runtime_dir=runtime_dir)
    watcher = RuntimeWatcher(runtime_dir=watch_runtime, queue=queue)
    # #711: baseline at dispatch time so a stale done.json (or any runtime
    # file) left by a prior coach run is recorded as already-seen and is not
    # emitted as new on the first scan — only post-dispatch writes advance
    # the phase. Without this the coach raced PLANNED→RED in 9 s on a
    # leftover done.json (coach-run-690-cb0a26c9).
    watcher.baseline()
    watcher.start()
    events_processed = 0

    try:
        while sm.phase not in (Phase.COMPLETE, Phase.MERGED, Phase.BLOCKED):
            if max_events is not None and events_processed >= max_events:
                break
            event = queue.get(timeout=5.0)
            if event is None:
                continue
            events_processed += 1
            t = _cold_start_proposed_transition(sm, event)
            if t is None:
                continue
            record = _make_phase_transition_record(
                ctx.coach_run_id, ctx.issue_number, t.src, t.dst
            )
            with transactional_decision(writer, record):
                pass
            sm.history.append(sm.phase)
            sm.phase = t.dst
            _logger.info(
                "coach watcher event advance",
                extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}",
                       "trigger": event.get("event_type", "watcher")},
            )
            _try_emit_telemetry(ctx.issue_number, t.src, t.dst)
            spawn_result = spawn_h(ctx, t)
            if spawn_result == HandlerResult.ERROR:
                _logger.error(
                    "coach watcher event spawn failed",
                    extra={"issue": ctx.issue_number, "phase": f"{t.src.value}→{t.dst.value}"},
                )
                sm.history.append(sm.phase)
                sm.phase = Phase.BLOCKED
                break
    finally:
        watcher.stop()
        try:
            watcher.persist_checkpoint()
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-01
            pass


def _resolve_waves(cfg: "Config") -> list[list[int]]:
    """Resolve the dependency-ordered wave plan for a cold-start run.

    A multi-issue run derives waves from the dependency graph via
    :func:`compute_waves`; a single issue — or a graph that fails to build or
    resolve — collapses to one wave holding every requested issue number.
    """
    if len(cfg.issue_numbers) <= 1:
        return [cfg.issue_numbers]
    plan = build_plan(cfg.issue_numbers)
    if not plan:
        return [cfg.issue_numbers]
    try:
        return compute_waves(plan)
    except ValueError:
        _logger.warning(
            "coach cold-start: compute_waves could not order issues "
            "(cyclic or unresolvable dependency) — falling back to a single "
            "wave holding every requested issue",
            extra={
                "event": "coach.cold_start.wave_resolution_fallback",
                "issue_numbers": cfg.issue_numbers,
                "fallback": "single_wave",
            },
        )
        return [cfg.issue_numbers]


def _drive_wave_concurrently(
    wave: list[int], drive_fn: Callable[[int], int],
) -> dict[int, int]:
    """Drive every member of one wave concurrently, joining before returning.

    One worker thread per issue (issue #730) — ``drive_fn(issue_num)`` returns
    that member's rc. The join over all threads is the barrier that preserves
    between-wave dependency ordering: the next wave cannot start until every
    member of this one is terminal. Returns ``{issue_num: rc}``.
    """
    results: dict[int, int] = {}
    results_lock = threading.Lock()

    def _worker(issue_num: int) -> None:
        rc = drive_fn(issue_num)
        with results_lock:
            results[issue_num] = rc

    threads = [
        threading.Thread(
            target=_worker, args=(issue_num,),
            name=f"coach-issue-{issue_num}",
        )
        for issue_num in wave
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _execute_cold_start(
    cfg: "Config",
    machines: list,
    runtime_dir: Path,
    *,
    _spawn_func: Optional[Callable] = None,
    _two_phase_func: Optional[Callable] = None,
    _injected_events: Optional[dict] = None,
    _max_loop_events: Optional[int] = None,
    _run_id_sink: Optional[list] = None,
    _observer_factory: Optional[Callable] = None,
) -> "ColdStartResult":
    """Wire and drive all issues through the full lifecycle (cold-start path).

    Waves run in dependency order (R6, issue #645): wave N+1 does not start
    until every member of wave N has reached a terminal state. Members WITHIN
    a single wave are driven concurrently — one worker thread per member, each
    with its own ``coach-run-*`` id and event loop — so the wave plan's
    ``Wave 0: #A,#B`` reflects real parallel execution (issue #730).

    A BLOCKED member is surfaced in the returned :class:`ColdStartResult`
    without aborting siblings that already started (Decision #1). Returns a
    ``ColdStartResult`` carrying the aggregate ``rc`` and the BLOCKED issues.

    Issue #754: starts exactly one MultiAgentObserver before driving waves;
    stops it after all waves complete regardless of outcome.
    """
    from atdd.coach.commands.observer import MultiAgentObserver as _MultiAgentObserver

    factory = _observer_factory or _MultiAgentObserver
    coach_observer = factory(runtime_dir)
    coach_observer.start()

    waves = _resolve_waves(cfg)
    machines_by_number = {sm.issue_number: sm for sm in machines}

    def _drive_issue(issue_num: int) -> int:
        """Drive one issue INIT→terminal, returning its rc.

        A crashed driver yields rc 2 rather than propagating, so one member's
        failure can never abort its siblings (issue #730, Decision #1).
        """
        sm = machines_by_number.get(issue_num)
        if sm is None:
            return 0
        try:
            return _drive_single_issue(
                cfg, sm, runtime_dir,
                _spawn_func=_spawn_func,
                _two_phase_func=_two_phase_func,
                _injected_events=(_injected_events or {}).get(issue_num),
                _max_loop_events=_max_loop_events,
                _run_id_sink=_run_id_sink,
            )
        except Exception:  # noqa: BLE001 — a crashed driver must not abort siblings
            _logger.exception(
                "coach cold-start: issue driver raised",
                extra={"issue": issue_num},
            )
            return 2

    aggregate_rc = 0
    blocked: list[int] = []
    try:
        for wave in waves:
            wave_results = _drive_wave_concurrently(wave, _drive_issue)
            # Aggregate this wave's outcomes — a BLOCKED member is recorded, not
            # fatal: siblings already running are left to finish.
            for issue_num, rc in wave_results.items():
                if rc != 0 and aggregate_rc == 0:
                    aggregate_rc = rc
                sm = machines_by_number.get(issue_num)
                if sm is not None and sm.phase == Phase.BLOCKED:
                    blocked.append(issue_num)
    finally:
        coach_observer.stop()

    return ColdStartResult(rc=aggregate_rc, blocked=blocked)


def _make_resume_transition_action(
    cfg: "Config", runtime_dir: Path
) -> Callable[[int, str, str], dict]:
    """Build the real per-transition orchestration action for ``--resume``.

    Mirrors the cold-start spawn dispatch (#645): for each pending transition
    the resumed runner walks, spawn that phase's persona via the same handler
    ``_drive_single_issue`` uses. A transition whose spawn handler returns
    ERROR raises, so ``ResumeRunner`` BLOCKs/escalates instead of paper-
    stamping the issue to COMPLETE (issue #734).
    """
    from atdd.coach.handlers import spawn as spawn_handler
    from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition

    def _action(issue: int, src: str, dst: str) -> dict:
        ctx = CoachContext(
            issue_number=issue,
            coach_run_id=cfg.resume or f"coach-resume-{issue}",
            runtime_dir=runtime_dir,
            dry_run=cfg.dry_run,
            multiplexer=cfg.multiplexer,
            multiplexer_mode=cfg.multiplexer_mode,
            llm=cfg.llm,
            persona_llm=cfg.persona_llm,
            judge_llm=cfg.judge_llm,
            require_issue_review=cfg.require_issue_review,
            review_phases=cfg.review_phases,
            skip_review=cfg.skip_review,
            risk_threshold_block=cfg.risk_threshold_block,
            allow_stale_suppressions=cfg.allow_stale_suppressions,
            auto_merge=cfg.auto_merge,
            max_retries=cfg.max_retries,
            escalation_channel=cfg.escalation_channel,
        )
        transition = Transition(Phase(src), Phase(dst))
        result = spawn_handler.handle(ctx, transition)
        if result == HandlerResult.ERROR:
            raise RuntimeError(
                f"#{issue}: resume orchestration failed at {src}->{dst} "
                f"(spawn handler returned ERROR)"
            )
        return {"transitioned": True, "new_phase": dst}

    return _action


def run(
    issue_numbers: list[int],
    max_retries: Optional[int] = None,
    escalation_channel: Optional[str] = None,
    multiplexer: Optional[str] = None,
    multiplexer_mode: str = "workspace",
    auto_merge: bool = False,
    strict_deps: bool = False,
    llm: Optional[str] = None,
    persona_llm: Optional[dict[str, str]] = None,
    judge_llm: Optional[str] = None,
    require_issue_review: str = "warn",
    review_phases: Optional[set[str]] = None,
    skip_review: bool = False,
    risk_threshold_block: Optional[int] = None,
    allow_stale_suppressions: bool = False,
    resume: Optional[str] = None,
    dry_run: bool = False,
    # --- Test seams (not exposed in CLI) — issue #645 cold-start wiring ---
    _runtime_dir_override: Optional[Path] = None,
    _max_loop_events: Optional[int] = None,
    _injected_events: Optional[dict] = None,
    _run_id_sink: Optional[list] = None,
    _spawn_func: Optional[Callable] = None,
    _two_phase_func: Optional[Callable] = None,
    _transition_action_override: Optional[Callable] = None,
) -> int:
    """Drive each issue through the full lifecycle via the cold-start path.

    On cold-start (no --resume, no --dry-run): wires DecisionWriter, spawn
    handler (K1), watcher event loop (J5), validator dispatch (M3), observer
    (L1), reviewer (N5), and two-phase commit (J4) into an event-driven loop
    that runs from INIT to MERGED (or halts at BLOCKED/REFACTOR-without-automerge).

    Issue #645 — cold-start wiring. Prior docstring: "No side effects beyond
    print" — that gap is what this issue closes.
    """
    cfg = Config(
        issue_numbers=issue_numbers,
        max_retries=max_retries,
        escalation_channel=escalation_channel,
        multiplexer=multiplexer,
        multiplexer_mode=multiplexer_mode,
        auto_merge=auto_merge,
        strict_deps=strict_deps,
        llm=llm,
        persona_llm=persona_llm or {},
        judge_llm=judge_llm,
        require_issue_review=require_issue_review,
        review_phases=review_phases or set(),
        skip_review=skip_review,
        risk_threshold_block=risk_threshold_block,
        allow_stale_suppressions=allow_stale_suppressions,
        resume=resume,
        dry_run=dry_run,
    )
    policy = resolve_policy(cfg)

    print(f"atdd coach: {len(cfg.issue_numbers)} issue(s); strict_deps={policy.strict_deps}")

    machines = [initialize_state_machine(num) for num in cfg.issue_numbers]
    print("Planned state path per issue:")
    for sm in machines:
        _print_planned_path(sm)

    if len(cfg.issue_numbers) > 1:
        plan = build_plan(cfg.issue_numbers)
        if plan:
            try:
                waves = compute_waves(plan)
            except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                print(f"❌ {exc}", file=sys.stderr)
                return 2
            print(f"Wave plan: {len(waves)} wave(s)")
            for i, wave in enumerate(waves):
                nums = ",".join(f"#{n}" for n in wave)
                print(f"  Wave {i}: {nums}")

    runtime_dir = _runtime_dir_override or Path(".atdd") / "runtime"

    if cfg.resume is not None:
        from atdd.coach.commands.durability import DecisionWriter
        from atdd.coach.commands.resume import ResumeRunner

        writer = DecisionWriter(runtime_dir=runtime_dir)
        # Wire ResumeRunner with a real transition_action so each pending
        # phase is genuinely orchestrated (persona spawn + work) rather than
        # paper-stamped to COMPLETE — issue #734.
        transition_action = _transition_action_override or _make_resume_transition_action(
            cfg, runtime_dir
        )
        runner = ResumeRunner(
            runtime_dir=runtime_dir,
            run_id=cfg.resume,
            decision_writer=writer,
            transition_action=transition_action,
        )
        reconstructed = runner.reconstruct()
        print(f"  --resume={cfg.resume!r}: reconstructed {len(reconstructed)} issue(s)")
        for issue, phase in sorted(reconstructed.items()):
            print(f"    #{issue}: {phase}")
        if not cfg.dry_run:
            try:
                final = runner.drive_to_complete(cfg.issue_numbers)
            except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-01
                # A phase the resume run could not legitimately complete must
                # BLOCK/escalate — never silently fast-forward to COMPLETE.
                for num in cfg.issue_numbers:
                    _write_escalation(
                        cfg.escalation_channel,
                        f"#{num}: resume blocked — {exc}",
                    )
                print(f"❌ resume blocked: {exc}", file=sys.stderr)
                return 1
            for issue, phase in sorted(final.items()):
                print(f"    #{issue} → {phase}")
        return 0

    # Cold-start execution path (issue #645): drive all issues from INIT to MERGED.
    if not cfg.dry_run:
        result = _execute_cold_start(
            cfg,
            machines,
            runtime_dir,
            _spawn_func=_spawn_func,
            _two_phase_func=_two_phase_func,
            _injected_events=_injected_events,
            _max_loop_events=_max_loop_events,
            _run_id_sink=_run_id_sink,
        )
        if result.blocked:
            print(
                f"⚠ BLOCKED: {', '.join(f'#{n}' for n in result.blocked)}",
                file=sys.stderr,
            )
        return result.rc

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    cfg = parse_cli(list(sys.argv[1:] if argv is None else argv))
    return run(
        issue_numbers=cfg.issue_numbers,
        max_retries=cfg.max_retries,
        escalation_channel=cfg.escalation_channel,
        multiplexer=cfg.multiplexer,
        multiplexer_mode=cfg.multiplexer_mode,
        auto_merge=cfg.auto_merge,
        strict_deps=cfg.strict_deps,
        llm=cfg.llm,
        persona_llm=cfg.persona_llm,
        judge_llm=cfg.judge_llm,
        require_issue_review=cfg.require_issue_review,
        review_phases=cfg.review_phases,
        skip_review=cfg.skip_review,
        risk_threshold_block=cfg.risk_threshold_block,
        allow_stale_suppressions=cfg.allow_stale_suppressions,
        resume=cfg.resume,
        dry_run=cfg.dry_run,
    )


# ---------------------------------------------------------------------------
# `atdd coach status` + top-level dispatch (#616 / L001)
# ---------------------------------------------------------------------------


def run_cli(argv: list[str]) -> int:
    """Top-level entry point forwarded from cli.py.

    Routes ``atdd coach status [...]`` to the status subcommand (coach_status.py)
    and all other invocations to the existing ``parse_cli`` + ``run`` path.
    """
    if argv and argv[0] == "status":
        return run_status(argv[1:])
    if argv and argv[0] == "review":
        return run_review(argv[1:])
    if argv and argv[0] == "watch":
        return run_watch(argv[1:])
    if argv and argv[0] == "gc":
        return run_gc(argv[1:])
    cfg = parse_cli(argv)
    return run(
        issue_numbers=cfg.issue_numbers,
        max_retries=cfg.max_retries,
        escalation_channel=cfg.escalation_channel,
        multiplexer=cfg.multiplexer,
        multiplexer_mode=cfg.multiplexer_mode,
        auto_merge=cfg.auto_merge,
        strict_deps=cfg.strict_deps,
        llm=cfg.llm,
        persona_llm=cfg.persona_llm,
        judge_llm=cfg.judge_llm,
        require_issue_review=cfg.require_issue_review,
        review_phases=cfg.review_phases,
        skip_review=cfg.skip_review,
        risk_threshold_block=cfg.risk_threshold_block,
        allow_stale_suppressions=cfg.allow_stale_suppressions,
        resume=cfg.resume,
        dry_run=cfg.dry_run,
    )
