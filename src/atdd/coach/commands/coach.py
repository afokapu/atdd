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
import json
import logging
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

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
from atdd.coach.commands.spawn import ADAPTER_REGISTRY, PERSONAS

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
    "prompt_persona_models",
    "should_prompt_for_models",
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
    multiplexer_mode: str = "surface"
    auto_merge: bool = False
    strict_deps: bool = False
    llm: Optional[str] = None
    persona_llm: dict[str, str] = field(default_factory=dict)
    judge_llm: Optional[str] = None
    require_issue_review: str = "warn"
    review_phases: set[str] = field(default_factory=lambda: {"refactor"})
    skip_review: bool = False
    risk_threshold_block: Optional[int] = None
    allow_stale_suppressions: bool = False
    resume: Optional[str] = None
    dry_run: bool = False
    stale_warn_minutes: Optional[int] = None
    no_progress_ttl: Optional[int] = None
    no_prompt: bool = False
    # TrainRunner backend (docs/coach-decomposition.md §7.4, Child 8). Only
    # "jsonl" is implemented; "temporal"/"langgraph" are reserved names that
    # raise NotImplementedError until §7.2/§7.3 land.
    runner: str = "jsonl"


@dataclass
class Policy:
    """Wave-transition gating policy derived from Config.

    J1 just carries `strict_deps` forward; downstream tracks consult it
    to decide whether a wave is allowed to advance with unresolved deps.
    """

    strict_deps: bool


@dataclass
class CoachConfig:
    """Per-issue coach configuration.

    Holds the resolved per-issue settings that the spawn pipeline reads.
    Distinct from ``Config`` (which is a CLI-level multi-issue bag).
    """

    issue: int = 0
    multiplexer_mode: str = "surface"
    llm: Optional[str] = None
    no_prompt: bool = False


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


class _MultiplexerHelpAction(argparse.Action):
    """Argparse action that prints the multiplexer primer and exits 0.

    Mirrors the ``--help`` pattern so it fires during parse_args before
    required-argument validation, allowing ``atdd coach --multiplexer-help``
    without supplying issue numbers.
    """

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default,
                         nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        import os as _os
        from atdd.coach.utils.multiplexer_primer import _BACKEND_FROM_ENV, _PRIMER_TEXT

        _env = _os.environ
        backend = next(
            (b for var, b in _BACKEND_FROM_ENV.items() if _env.get(var)),
            "cmux",
        )
        sys.stdout.write(_PRIMER_TEXT.get(backend, _PRIMER_TEXT["cmux"]))
        parser.exit(0)


def resolve_multiplexer_mode(explicit_flag: Optional[str], env: Optional[dict] = None) -> str:
    """Return the effective multiplexer mode.

    If *explicit_flag* is not None it wins. Otherwise always returns
    ``'surface'`` — the canonical cmux RPC path (issue #830). The
    legacy ``'pane'`` and ``'workspace'`` modes used cmux new-pane /
    new-workspace which fail with Broken pipe on cmux >=0.64.7.
    """
    if explicit_flag is not None:
        return explicit_flag
    return "surface"


def resolve_no_prompt(explicit_flag: Optional[bool], isatty: bool) -> bool:
    """Return the effective no-prompt flag.

    If *explicit_flag* is not None it wins (True = skip prompt, False = force
    prompt). Otherwise return True (skip prompt) when *isatty* is False so
    non-interactive invocations never hang on the model-selection prompt.
    """
    if explicit_flag is not None:
        return bool(explicit_flag)
    return not isatty


def _build_coach_config_from_ns(ns: object) -> dict:
    """Extract the no_prompt resolution from a parsed argparse Namespace.

    Called by parse_cli to wire resolve_no_prompt into CoachConfig construction.
    Returns a dict of overrides to apply on top of the namespace values.
    """
    import sys as _sys
    explicit_no_prompt = getattr(ns, "no_prompt", None)
    if explicit_no_prompt is False:
        explicit_no_prompt = None
    isatty = _sys.stdin.isatty()
    return {"no_prompt": resolve_no_prompt(explicit_flag=explicit_no_prompt, isatty=isatty)}


def _handle_multiplexer_help(ns: object, env: Optional[dict] = None) -> None:
    """Print the multiplexer primer and exit 0 when --multiplexer-help is set."""
    import os as _os
    from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer, _BACKEND_FROM_ENV, _PRIMER_TEXT

    if not getattr(ns, "multiplexer_help", False):
        return
    _env = env if env is not None else _os.environ
    backend = next(
        (b for var, b in _BACKEND_FROM_ENV.items() if _env.get(var)),
        "cmux",
    )
    primer_text = _PRIMER_TEXT.get(backend, _PRIMER_TEXT["cmux"])
    sys.stdout.write(primer_text)
    sys.exit(0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach",
        description=(
            "Durable per-issue orchestrator (coach v9). J1 skeleton: state "
            "machine + CLI surface only; watchers/validators/observers/spawn "
            "live in adjacent tracks."
        ),
        epilog=(
            "Environment variables:\n"
            "  ATDD_WORKER_READY_TIMEOUT  Worker boot timeout in seconds (default: 30).\n"
            "                             Increase for slow machines or cold worktrees.\n"
            "\n"
            "Recovery: cold-start is idempotent — re-run atdd coach <N> after fixing\n"
            "  the underlying issue (missing multiplexer, wrong --repo path, etc.).\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        choices=["surface"],
        default=None,
        dest="multiplexer_mode",
        help=(
            "Surface creation strategy. Only 'surface' is supported: uses "
            "cmux new-surface --pane <ref>. The legacy 'workspace' and 'pane' "
            "modes are removed — they called deprecated cmux RPCs that fail "
            "with Broken pipe on cmux >=0.64.7 (issue #830)."
        ),
    )
    parser.add_argument(
        "--multiplexer-help",
        action=_MultiplexerHelpAction,
        help="Print the multiplexer quick-reference and exit.",
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
        default=None,
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
        help=argparse.SUPPRESS,
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
    parser.add_argument(
        "--no-progress-ttl",
        type=int,
        default=None,
        dest="no_progress_ttl",
        metavar="MINUTES",
        help=(
            "Self-terminate after MINUTES of no phase advance (zombie guard, #724). "
            "Escalates to --escalation-channel before exiting."
        ),
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        dest="no_prompt",
        help=(
            "Skip the interactive per-persona model prompt even on a TTY. "
            "Use this for scripted runs where --persona-llm is not given."
        ),
    )
    parser.add_argument(
        "--runner",
        type=str,
        choices=["jsonl", "temporal", "langgraph"],
        default="jsonl",
        dest="runner",
        help=(
            "TrainRunner backend (docs/coach-decomposition.md §7.4). Only 'jsonl' "
            "is implemented; 'temporal'/'langgraph' are reserved and raise "
            "NotImplementedError until §7.2/§7.3 land."
        ),
    )
    return parser


_make_coach_parser = _build_parser


def parse_cli(argv: list[str]) -> Config:
    import os as _os
    ns = _build_parser().parse_args(argv)
    _handle_multiplexer_help(ns)
    _no_prompt_overrides = _build_coach_config_from_ns(ns)
    return Config(
        issue_numbers=ns.issue_numbers,
        max_retries=ns.max_retries,
        escalation_channel=ns.escalation_channel,
        multiplexer=ns.multiplexer,
        multiplexer_mode=resolve_multiplexer_mode(
            explicit_flag=ns.multiplexer_mode, env=_os.environ
        ),
        auto_merge=ns.auto_merge,
        strict_deps=ns.strict_deps,
        llm=ns.llm,
        persona_llm=ns.persona_llm,
        judge_llm=ns.judge_llm,
        require_issue_review=ns.require_issue_review,
        review_phases=ns.review_phases if ns.review_phases is not None else {"refactor"},
        skip_review=ns.skip_review,
        risk_threshold_block=ns.risk_threshold_block,
        allow_stale_suppressions=ns.allow_stale_suppressions,
        resume=ns.resume,
        dry_run=ns.dry_run,
        stale_warn_minutes=ns.stale_warn_minutes,
        no_progress_ttl=ns.no_progress_ttl,
        no_prompt=_no_prompt_overrides["no_prompt"],
        runner=getattr(ns, "runner", "jsonl"),
    )


def resolve_policy(cfg: Config) -> Policy:
    return Policy(strict_deps=cfg.strict_deps)


# ---------------------------------------------------------------------------
# TrainRunner selection (docs/coach-decomposition.md §7.4, Child 8 / #895)
# ---------------------------------------------------------------------------

_DOC_REF = "docs/coach-decomposition.md"


def _require_supported_runner(runner: str) -> str:
    """Return ``runner`` when implemented; raise for the reserved backends.

    Only the default JSONL runner ships (§7.1). ``temporal`` and ``langgraph``
    are reserved names (§7.2/§7.3) — selecting them raises ``NotImplementedError``
    with a message pointing at this document, per R-9.
    """
    if runner == "jsonl":
        return runner
    if runner == "temporal":
        raise NotImplementedError(
            "the Temporal TrainRunner backend is reserved but not implemented; "
            f"see {_DOC_REF} §7.2"
        )
    if runner == "langgraph":
        raise NotImplementedError(
            "the LangGraph review subgraph is reserved but not implemented; "
            f"see {_DOC_REF} §7.3"
        )
    raise NotImplementedError(
        f"unknown TrainRunner backend {runner!r}; only 'jsonl' is implemented "
        f"(see {_DOC_REF} §7.4)"
    )


def _repo_root_for(runtime_dir: Path) -> Path:
    """Resolve the repo root the persistence store + conventions load against.

    Production ``runtime_dir`` is ``<repo>/.atdd/runtime``; a test override is an
    arbitrary tmp dir, in which case the current working directory is the repo.
    """
    rt = Path(runtime_dir).resolve()
    if rt.name == "runtime" and rt.parent.name == ".atdd":
        return rt.parent.parent
    return Path.cwd()


def _build_train_runner(cfg: "Config", runtime_dir: Path):
    """Instantiate the configured TrainRunner (Child 8, §7.1/§7.4).

    Only ``jsonl`` is implemented; ``_require_supported_runner`` has already
    rejected the reserved backends by the time this is called.
    """
    from atdd.train.persistence import JsonlPersistenceStore
    from atdd.train.runners.jsonl import JsonlTrainRunner

    repo_root = _repo_root_for(runtime_dir)
    store = JsonlPersistenceStore(repo_root)
    return JsonlTrainRunner(persistence=store, cfg=cfg, runtime_dir=runtime_dir)


def _build_policy_handle(runtime_dir: Path):
    """Construct the PolicyHandle the runner drives with (coach-core + frozen conventions)."""
    from atdd.coach import core as coach_core
    from atdd.train.persistence import load_conventions
    from atdd.train.runner_iface import PolicyHandle

    repo_root = _repo_root_for(runtime_dir)
    return PolicyHandle(coach_module=coach_core, conventions=load_conventions(repo_root))


# ---------------------------------------------------------------------------
# Interactive model selection (issue #723 / E008)
# ---------------------------------------------------------------------------


def prompt_persona_models(
    personas: Iterable[str],
    known_models: Sequence[str],
    *,
    stdin=None,
    stdout=None,
) -> dict[str, str]:
    """Interactively prompt the operator for a model per persona.

    Reads one line per persona from *stdin* (defaults to ``sys.stdin``).
    Rejects unknown model ids and re-prompts until a valid id is entered.
    Returns a dict mapping each persona name to the chosen model id.
    """
    _in = stdin if stdin is not None else sys.stdin
    _out = stdout if stdout is not None else sys.stdout

    valid = sorted(known_models)
    model_list = " / ".join(valid)
    result: dict[str, str] = {}

    for persona in personas:
        while True:
            _out.write(f"  {persona} model [{model_list}]: ")
            _out.flush()
            line = _in.readline().strip()
            if line in valid:
                result[persona] = line
                break
            _out.write(
                f"  ✗ {line!r} is not a registered model id."
                f" Valid: {model_list}\n"
            )
            _out.flush()

    return result


def should_prompt_for_models(
    cfg: Config,
    isatty_fn: Optional[Callable[[], bool]] = None,
) -> bool:
    """Return True when the interactive per-persona model prompt should fire.

    The prompt fires only when ALL of the following hold:
    - stdin is a TTY (``isatty_fn()`` returns True)
    - ``cfg.persona_llm`` is empty (``--persona-llm`` was not given)
    - ``cfg.no_prompt`` is False (``--no-prompt`` was not given)
    """
    _isatty = isatty_fn if isatty_fn is not None else sys.stdin.isatty
    return bool(_isatty() and not cfg.persona_llm and not cfg.no_prompt)


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


# ---------------------------------------------------------------------------
# Warm-resume + label-sync helpers (Y001, Y002)
# ---------------------------------------------------------------------------

_PHASE_LABELS_ALL: frozenset[str] = frozenset({
    "atdd:INIT", "atdd:PLANNED", "atdd:RED", "atdd:GREEN",
    "atdd:SMOKE", "atdd:REFACTOR", "atdd:COMPLETE", "atdd:BLOCKED",
})

# Phases for which coach should warm-resume (spawn next persona from current state)
# rather than restart from INIT. COMPLETE/BLOCKED/OBSOLETE are intentionally excluded.
_WARM_RESUME_PHASES: frozenset[Phase] = frozenset({
    Phase.PLANNED, Phase.RED, Phase.GREEN, Phase.SMOKE, Phase.REFACTOR,
})


def _read_current_github_phase(issue_number: int) -> Optional[Phase]:
    """Return the Phase corresponding to the live atdd:<phase> label, or None."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number),
             "--json", "labels", "--jq", "[.labels[].name]"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            return None
        labels = json.loads(result.stdout.strip())
        for label in labels:
            if label.startswith("atdd:") and label != "atdd-issue":
                phase_str = label[len("atdd:"):]
                phase = _PHASE_TRAILER_MAP.get(phase_str)
                if phase is not None:
                    return phase
    except Exception as exc:
        _logger.warning("_read_current_github_phase failed", extra={"issue": issue_number, "error": str(exc)})
    return None


def _gh_remove_phase_labels(issue_number: int, labels: list) -> None:
    """Remove labels from a GitHub issue via gh CLI."""
    for label in labels:
        try:
            subprocess.run(
                ["gh", "issue", "edit", str(issue_number), "--remove-label", label],
                capture_output=True, text=True, check=False,
            )
        except Exception as exc:
            _logger.warning("_gh_remove_phase_labels failed", extra={"issue": issue_number, "label": label, "error": str(exc)})


def _gh_add_label(issue_number: int, labels: list) -> None:
    """Add labels to a GitHub issue via gh CLI."""
    if not labels:
        return
    try:
        subprocess.run(
            ["gh", "issue", "edit", str(issue_number), "--add-label", ",".join(labels)],
            capture_output=True, text=True, check=False,
        )
    except Exception as exc:
        _logger.warning("_gh_add_label failed", extra={"issue": issue_number, "labels": labels, "error": str(exc)})


def _swap_phase_label(issue_number: int, new_phase: Phase) -> None:
    """Remove all atdd:<phase> labels and add atdd:<new_phase> on the GitHub issue."""
    _gh_remove_phase_labels(issue_number, list(_PHASE_LABELS_ALL))
    _gh_add_label(issue_number, [f"atdd:{new_phase.value}"])


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


def _check_no_progress_ttl(
    last_advance_at: float,
    no_progress_ttl_seconds: int,
    escalation_channel: Optional[str],
    issue_number: int,
    current_phase: Phase,
) -> bool:
    """Return True and escalate if elapsed time since last phase advance exceeds the TTL."""
    elapsed = time.monotonic() - last_advance_at
    if elapsed <= no_progress_ttl_seconds:
        return False
    _write_escalation(
        escalation_channel,
        f"#{issue_number}: no progress for {int(elapsed)}s (TTL {no_progress_ttl_seconds}s) "
        f"at phase {current_phase.value}; self-terminating",
    )
    return True


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
    from atdd.runtime import worktree as runtime_worktree

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

    # Worktree creation (triage of an existing non-git path, remote/new-branch
    # selection, and the I-1/I-2/I-9 incident defenses) is owned by the runtime
    # layer (docs/coach-decomposition.md §13.5). Coach only resolves the path
    # and branch, then delegates.
    try:
        return runtime_worktree.ensure_issue_worktree(
            worktree, branch, repo_root, issue_number=ctx.issue_number,
        )
    except runtime_worktree.ProtectedBranchError as exc:
        _logger.warning(
            "coach cold-start refused worktree on protected branch",
            extra={"issue": ctx.issue_number, "error": str(exc)},
        )
        print(
            f"❌ #{ctx.issue_number}: {exc}",
            file=sys.stderr,
        )
        return None


def _make_coach_context(
    cfg: "Config",
    issue_number: int,
    coach_run_id: str,
    runtime_dir: Path,
    *,
    multiplexer_backend: Optional[object] = None,
    worktree_override: Optional[Path] = None,
) -> "CoachContext":
    """Build a ``CoachContext`` from the run ``Config`` for one issue.

    Single construction site shared by the cold-start path
    (``_drive_single_issue``) and the ``--resume`` path
    (``_make_resume_transition_action``). Decision #1 of issue #734: one
    orchestration path is less drift-prone than two — both must spawn
    personas with an identically-shaped context, so the mapping from
    ``Config`` lives here once instead of being copied per call site.

    ``multiplexer_backend`` / ``worktree_override`` are explicit
    orchestration seams (both ``None`` in production): they let a caller
    inject collaborators by construction so hermetic integration tests
    need not monkeypatch ``_resolve_multiplexer`` / ``_resolve_worktree``.
    """
    from atdd.coach.handlers.state_machine import CoachContext

    return CoachContext(
        issue_number=issue_number,
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
        multiplexer_backend=multiplexer_backend,
        worktree_override=worktree_override,
    )


def _load_issue_context(issue: int, cfg: "Config") -> object:
    """Load per-issue context (stub — full implementation in downstream track)."""
    return None


def _pre_flight_checks(cfg: "Config") -> None:
    """Run pre-flight validation (stub — full implementation in downstream track)."""
    return None


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
    """DEPRECATED shim — moved to atdd.train.issue_runner.drive_single_issue (Child 8, #895).

    Removal target: 3.87.0 (§11 deprecation cadence). New code drives an issue via
    ``JsonlTrainRunner.start_issue``; this name is kept so existing internal/test
    callers keep working through the soak.
    """
    import warnings
    from atdd.train import issue_runner as _issue_runner

    warnings.warn(
        "atdd.coach.commands.coach._drive_single_issue is deprecated; the per-issue "
        "drive moved to atdd.train.issue_runner.drive_single_issue (Child 8). "
        "Removal target: 3.87.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _issue_runner.drive_single_issue(
        cfg, sm, runtime_dir,
        _spawn_func=_spawn_func,
        _two_phase_func=_two_phase_func,
        _injected_events=_injected_events,
        _max_loop_events=_max_loop_events,
        _run_id_sink=_run_id_sink,
    )


def _process_injected_events(
    ctx: "CoachContext",
    sm: StateMachine,
    events: list,
    writer: "DecisionWriter",
    spawn_h: Callable,
) -> None:
    """DEPRECATED shim — moved to atdd.train.issue_runner._process_injected_events (Child 8, #895).

    Removal target: 3.87.0 (§11).
    """
    import warnings
    from atdd.train import issue_runner as _issue_runner

    warnings.warn(
        "atdd.coach.commands.coach._process_injected_events is deprecated; moved to "
        "atdd.train.issue_runner (Child 8). Removal target: 3.87.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _issue_runner._process_injected_events(ctx, sm, events, writer, spawn_h)


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
    no_progress_ttl_seconds: Optional[int] = None,
) -> None:
    """DEPRECATED shim — moved to atdd.train.issue_runner._process_watcher_events (Child 8, #895).

    Removal target: 3.87.0 (§11).
    """
    import warnings
    from atdd.train import issue_runner as _issue_runner

    warnings.warn(
        "atdd.coach.commands.coach._process_watcher_events is deprecated; moved to "
        "atdd.train.issue_runner (Child 8). Removal target: 3.87.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _issue_runner._process_watcher_events(
        ctx, sm, runtime_dir, cfg, writer, spawn_h,
        max_events=max_events,
        no_progress_ttl_seconds=no_progress_ttl_seconds,
    )


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
    runner: Optional[object] = None,
    policy: Optional[object] = None,
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

    Child 8 (#895): when ``runner`` (a :class:`~atdd.train.runner_iface.TrainRunner`)
    and ``policy`` are supplied, each issue is driven through
    ``runner.start_issue`` — the TrainRunner seam — instead of the deprecated
    ``_drive_single_issue`` private call. The legacy direct-drive path is kept
    only as the ``runner is None`` fallback so the existing wave-orchestration
    tests, which inject a fake ``_drive_single_issue``, keep working.
    """
    from atdd.coach.commands.observer import MultiAgentObserver as _MultiAgentObserver

    factory = _observer_factory or _MultiAgentObserver
    coach_observer = factory(runtime_dir)
    coach_observer.start()

    waves = _resolve_waves(cfg)
    machines_by_number = {sm.issue_number: sm for sm in machines}
    if runner is not None:
        # Drive the same StateMachine objects the wave bookkeeping inspects, and
        # thread the cold-start drive seams through the runner so start_issue
        # reproduces the previous _drive_single_issue call exactly.
        runner.bind_state_machines(machines_by_number)
        runner.bind_drive_context(
            cfg=cfg,
            runtime_dir=runtime_dir,
            spawn_func=_spawn_func,
            two_phase_func=_two_phase_func,
            max_loop_events=_max_loop_events,
            run_id_sink=_run_id_sink,
            injected_events=_injected_events,
        )

    def _drive_issue(issue_num: int) -> int:
        """Drive one issue INIT→terminal, returning its rc.

        A crashed driver yields rc 2 rather than propagating, so one member's
        failure can never abort its siblings (issue #730, Decision #1).
        """
        sm = machines_by_number.get(issue_num)
        if sm is None:
            return 0
        try:
            if runner is not None:
                run_id = runner.start_issue(issue_num, policy=policy)
                return runner.rc_for(run_id)
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
    cfg: "Config",
    runtime_dir: Path,
    *,
    multiplexer_backend: Optional[object] = None,
    worktree_override: Optional[Path] = None,
) -> Callable[[int, str, str], dict]:
    """DEPRECATED shim — moved to atdd.train.issue_runner.make_resume_transition_action (Child 8, #895).

    Removal target: 3.87.0 (§11).
    """
    import warnings
    from atdd.train import issue_runner as _issue_runner

    warnings.warn(
        "atdd.coach.commands.coach._make_resume_transition_action is deprecated; moved "
        "to atdd.train.issue_runner.make_resume_transition_action (Child 8). "
        "Removal target: 3.87.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _issue_runner.make_resume_transition_action(
        cfg, runtime_dir,
        multiplexer_backend=multiplexer_backend,
        worktree_override=worktree_override,
    )


def run(
    issue_numbers: list[int],
    max_retries: Optional[int] = None,
    escalation_channel: Optional[str] = None,
    multiplexer: Optional[str] = None,
    multiplexer_mode: str = "surface",
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
    runner: str = "jsonl",
    # --- Test seams (not exposed in CLI) — issue #645 cold-start wiring ---
    _runtime_dir_override: Optional[Path] = None,
    _max_loop_events: Optional[int] = None,
    _injected_events: Optional[dict] = None,
    _run_id_sink: Optional[list] = None,
    _spawn_func: Optional[Callable] = None,
    _two_phase_func: Optional[Callable] = None,
    _transition_action_override: Optional[Callable] = None,
    _multiplexer_backend: Optional[object] = None,
    _worktree_override: Optional[Path] = None,
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
        review_phases=review_phases if review_phases is not None else {"refactor"},
        skip_review=skip_review,
        risk_threshold_block=risk_threshold_block,
        allow_stale_suppressions=allow_stale_suppressions,
        resume=resume,
        dry_run=dry_run,
        runner=runner,
    )
    policy = resolve_policy(cfg)
    # Fail fast on a reserved-but-unimplemented runner backend (§7.4 / R-9).
    _require_supported_runner(cfg.runner)

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
            cfg,
            runtime_dir,
            multiplexer_backend=_multiplexer_backend,
            worktree_override=_worktree_override,
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
        # Child 8 (#895): drive each issue through the TrainRunner seam. The CLI
        # instantiates JsonlTrainRunner + PolicyHandle here and hands them to the
        # cold-start loop, which calls runner.start_issue per issue — no direct
        # coach.commands.coach._drive_* private call remains in the CLI path.
        train_runner = _build_train_runner(cfg, runtime_dir)
        result = _execute_cold_start(
            cfg,
            machines,
            runtime_dir,
            _spawn_func=_spawn_func,
            _two_phase_func=_two_phase_func,
            _injected_events=_injected_events,
            _max_loop_events=_max_loop_events,
            _run_id_sink=_run_id_sink,
            runner=train_runner,
            policy=_build_policy_handle(runtime_dir),
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
    if should_prompt_for_models(cfg):
        known = sorted(ADAPTER_REGISTRY)
        print("Select the LLM adapter for each persona:")
        cfg.persona_llm = prompt_persona_models(PERSONAS, known)
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
        runner=cfg.runner,
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
    if should_prompt_for_models(cfg):
        known = sorted(ADAPTER_REGISTRY)
        print("Select the LLM adapter for each persona:")
        cfg.persona_llm = prompt_persona_models(PERSONAS, known)
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
        runner=cfg.runner,
    )
