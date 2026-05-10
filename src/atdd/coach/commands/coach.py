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
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# Per spec §0.2 absorption discipline: reuse, do not redefine.
# P5 (#531): orchestrate.py archived; import from _archived.
from atdd.coach.commands._archived.orchestrate import build_plan, compute_waves


class Phase(str, Enum):
    """Per-issue lifecycle states (spec §4.1).

    `str` mixin gives a stable string serialization for the eventual
    decision-log writer (#J3); J1 itself never writes the log.
    """

    INIT = "INIT"
    PLANNED = "PLANNED"
    RED = "RED"
    GREEN = "GREEN"
    SMOKE = "SMOKE"
    REFACTOR = "REFACTOR"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    MERGED = "MERGED"

    def __str__(self) -> str:
        return self.value


TRANSITION_TABLE: dict[Phase, set[Phase]] = {
    Phase.INIT:     {Phase.PLANNED, Phase.BLOCKED},
    Phase.PLANNED:  {Phase.RED, Phase.BLOCKED},
    Phase.RED:      {Phase.GREEN, Phase.BLOCKED},
    Phase.GREEN:    {Phase.SMOKE, Phase.BLOCKED},
    Phase.SMOKE:    {Phase.REFACTOR, Phase.BLOCKED},
    Phase.REFACTOR: {Phase.COMPLETE, Phase.BLOCKED},
    Phase.COMPLETE: {Phase.MERGED},
    Phase.BLOCKED:  {
        Phase.INIT, Phase.PLANNED, Phase.RED,
        Phase.GREEN, Phase.SMOKE, Phase.REFACTOR,
    },
    Phase.MERGED:   set(),
}


def can_transition(src: Phase, dst: Phase) -> bool:
    return dst in TRANSITION_TABLE[src]


PLANNED_PATH: tuple[Phase, ...] = (
    Phase.INIT, Phase.PLANNED, Phase.RED, Phase.GREEN,
    Phase.SMOKE, Phase.REFACTOR, Phase.COMPLETE, Phase.MERGED,
)


@dataclass
class StateMachine:
    """Per-issue state container. J1 ships the structure; transition
    handlers land in per-state issues across the J/K/L/M tracks."""

    issue_number: int
    phase: Phase = Phase.INIT
    history: list[Phase] = field(default_factory=list)


def initialize_state_machine(issue_number: int) -> StateMachine:
    return StateMachine(issue_number=issue_number, phase=Phase.INIT)


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


@dataclass
class Policy:
    """Wave-transition gating policy derived from Config.

    J1 just carries `strict_deps` forward; downstream tracks consult it
    to decide whether a wave is allowed to advance with unresolved deps.
    """

    strict_deps: bool


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
        "--escalation-channel", type=str, default=None, dest="escalation_channel"
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
    )


def resolve_policy(cfg: Config) -> Policy:
    return Policy(strict_deps=cfg.strict_deps)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _print_planned_path(sm: StateMachine) -> None:
    arrow = " → ".join(p.value for p in PLANNED_PATH)
    print(f"  #{sm.issue_number}: {sm.phase.value} ({arrow})")


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
) -> int:
    """Initialize a per-issue state machine and print the planned path.

    No side effects beyond `print`. Watcher attachment, validator dispatch,
    observer integration, spawn integration, two-phase commit, decision
    durability, and resume reconstruction all live in adjacent tracks.
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

    if cfg.resume is not None:
        from atdd.coach.commands.durability import DecisionWriter
        from atdd.coach.commands.resume import ResumeRunner

        runtime_dir = Path(".atdd") / "runtime"
        writer = DecisionWriter(runtime_dir=runtime_dir)
        runner = ResumeRunner(
            runtime_dir=runtime_dir,
            run_id=cfg.resume,
            decision_writer=writer,
        )
        reconstructed = runner.reconstruct()
        print(f"  --resume={cfg.resume!r}: reconstructed {len(reconstructed)} issue(s)")
        for issue, phase in sorted(reconstructed.items()):
            print(f"    #{issue}: {phase}")
        if not cfg.dry_run:
            final = runner.drive_to_complete(cfg.issue_numbers)
            for issue, phase in sorted(final.items()):
                print(f"    #{issue} → {phase}")

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
