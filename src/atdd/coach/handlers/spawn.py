"""Spawn handler — K1 wiring (issue #585).

Invoked at each phase transition by the coach state machine. Maps the
transition to a (persona, phase) pair per spec §4.1, loads the per-phase
prompt YAML, then delegates to ``cmd_spawn`` from ``commands/spawn.py``.

Persona-per-transition table (spec §4.1):
  INIT → PLANNED  : planner
  PLANNED → RED   : tester
  RED → GREEN     : coder
  GREEN → SMOKE   : tester
  SMOKE → REFACTOR: coder

  REFACTOR → COMPLETE is reviewer-driven via N5 (#589) and is intentionally
  absent from this table.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition

# ---------------------------------------------------------------------------
# Persona-per-transition mapping (spec §4.1)
# ---------------------------------------------------------------------------

_TRANSITION_PERSONA: dict[tuple[Phase, Phase], str] = {
    (Phase.INIT, Phase.PLANNED): "planner",
    (Phase.PLANNED, Phase.RED): "tester",
    (Phase.RED, Phase.GREEN): "coder",
    (Phase.GREEN, Phase.SMOKE): "tester",
    (Phase.SMOKE, Phase.REFACTOR): "coder",
}

# The "phase" label passed to cmd_spawn corresponds to the destination phase
# (the deliverable the spawned persona is producing).
_TRANSITION_PHASE: dict[tuple[Phase, Phase], str] = {
    (Phase.INIT, Phase.PLANNED): "planned",
    (Phase.PLANNED, Phase.RED): "red",
    (Phase.RED, Phase.GREEN): "green",
    (Phase.GREEN, Phase.SMOKE): "smoke",
    (Phase.SMOKE, Phase.REFACTOR): "refactor",
}

# Module-level path roots — tests monkeypatch these to redirect I/O.
_PROMPTS_ROOT: Path = Path(__file__).parent.parent / "prompts" / "persona"
_RUNTIME_ROOT: Path = Path(".atdd") / "runtime"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class PromptNotFoundError(Exception):
    pass


def _load_persona_prompt(
    persona: str, phase: str, prompts_root: Optional[Path] = None
) -> str:
    """Load the prompt text from ``<prompts_root>/<persona>/<phase>.prompt.yaml``.

    Raises ``PromptNotFoundError`` when the file is absent or cannot be parsed.
    """
    root = prompts_root if prompts_root is not None else _PROMPTS_ROOT
    prompt_file = root / persona / f"{phase}.prompt.yaml"
    if not prompt_file.is_file():
        raise PromptNotFoundError(
            f"Missing persona prompt: {prompt_file}. "
            f"Expected at src/atdd/coach/prompts/persona/{persona}/{phase}.prompt.yaml"
        )
    try:
        import yaml
        data = yaml.safe_load(prompt_file.read_text())
    except Exception as exc:
        raise PromptNotFoundError(
            f"Failed to parse persona prompt {prompt_file}: {exc}"
        ) from exc
    return data.get("prompt") or ""


def _resolve_llm(ctx: CoachContext, persona: str) -> str:
    """Resolve the LLM for this persona: persona_llm map → ctx.llm → default."""
    return ctx.persona_llm.get(persona) or ctx.llm or "claude-code"


def _resolve_worktree(ctx: CoachContext) -> Path:
    """Derive the worktree path for the issue from its branch metadata."""
    from atdd.coach.commands import session_template
    fetched = session_template.fetch_issue(ctx.issue_number) or {}
    body = fetched.get("body") or ""
    meta = session_template.parse_metadata(body)
    branch = meta.get("Branch") or ""
    if branch and branch not in ("TBD", ""):
        slug = branch.replace("/", "-")
        return Path.cwd().parent / slug
    return Path.cwd().parent / f"issue-{ctx.issue_number}"


def _write_blocked_decision(
    ctx: CoachContext,
    transition: Transition,
    reason: str,
    run_id: str,
    runtime_root: Path,
) -> None:
    """Append a BLOCKED abort decision to ``<runtime_root>/coach/decisions.jsonl``."""
    from datetime import datetime, timezone
    from atdd.coach.commands.durability import DecisionWriter
    writer = DecisionWriter(runtime_dir=runtime_root)
    decision_id = str(uuid.uuid4())
    now = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    writer.append({
        "decision_id": decision_id,
        "timestamp": now,
        "coach_run_id": run_id,
        "issue_number": ctx.issue_number,
        "decision_type": "abort",
        "inputs": {
            "phase_src": transition.src.value,
            "phase_dst": transition.dst.value,
            "reason": reason,
        },
        "outcome": {
            "status": "BLOCKED",
            "action": "none",
        },
    })


def _call_spawn(
    ctx: CoachContext,
    persona: str,
    phase: str,
    llm: str,
    persona_prompt_content: str,
    worktree: Path,
    agent_id: str,
    runtime_root: Path,
) -> dict:
    """Thin wrapper around ``cmd_spawn`` for test-seam isolation."""
    from atdd.coach.commands.spawn import cmd_spawn
    return cmd_spawn(
        persona=persona,
        llm=llm,
        worktree=worktree,
        issue=ctx.issue_number,
        agent_id=agent_id,
        runtime_root=runtime_root,
        phase=phase,
        persona_prompt_content=persona_prompt_content,
        multiplexer_mode=ctx.multiplexer_mode,
        # Issue #730: reuse the issue's persistent surface if one exists —
        # cmd_spawn respawns the persona agent in place instead of spawning
        # a new pane.
        existing_surface_ref=ctx.issue_surface_ref,
    )


# Flaky multiplexer-IPC failures: a transient cmux/tmux socket hiccup recovers
# on a retry, unlike a genuine spawn failure (bad prompt, missing worktree).
# Matched case-insensitively against the exception text.
_TRANSIENT_SPAWN_ERROR_MARKERS = (
    "broken pipe",
    "failed to write to socket",
    "errno 32",
    "connection reset",
    "resource temporarily unavailable",
)

# Extra retries granted to transient IPC failures, *free of* ``max_retries``.
# A flaky cmux hiccup must never abort the coach (#715).
_MAX_TRANSIENT_SPAWN_RETRIES = 3


def _is_transient_spawn_error(exc: BaseException) -> bool:
    """True for flaky multiplexer-IPC failures worth retrying regardless of the
    configured ``max_retries`` budget (broken pipe, socket-write failure)."""
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_SPAWN_ERROR_MARKERS)


def _spawn_with_retries(
    ctx: CoachContext,
    transition: Transition,
    persona: str,
    phase: str,
    llm: str,
    persona_prompt_content: str,
    worktree: Path,
    base_agent_id: str,
    runtime_root: Path,
) -> Optional[dict]:
    """Call ``_call_spawn``, retrying on failure with exponential backoff.

    Genuine failures honour ``ctx.max_retries`` (``max_retries + 1`` attempts,
    default 1 — fail fast so real bugs surface). Flaky cmux/tmux IPC failures
    (broken pipe, socket-write) get up to ``_MAX_TRANSIENT_SPAWN_RETRIES`` extra
    attempts, *free of* that budget, so a transient multiplexer hiccup never
    aborts the coach (#715).

    Returns the result dict on success, or ``None`` after all attempts fail.
    Backoff: 1 s, 2 s, 4 s, … (doubles each retry, capped at 8 s).
    """
    max_retries = ctx.max_retries or 0
    transient_budget = _MAX_TRANSIENT_SPAWN_RETRIES
    delay = 1.0
    attempt = 0

    while True:
        if attempt > 0:
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
        agent_id = f"{base_agent_id}-{attempt}" if attempt > 0 else base_agent_id
        try:
            return _call_spawn(
                ctx, persona, phase, llm,
                persona_prompt_content, worktree, agent_id, runtime_root,
            )
        except Exception as exc:
            transient = _is_transient_spawn_error(exc) and transient_budget > 0
            print(
                f"⚠ spawn attempt {attempt + 1} failed for "
                f"#{ctx.issue_number} ({persona}/{phase})"
                f"{' [transient cmux IPC — retrying free of budget]' if transient else ''}"
                f": {exc}",
                file=sys.stderr,
            )
            attempt += 1
            if transient:
                transient_budget -= 1
                continue
            if attempt <= max_retries:
                continue
            # Genuine failure, retry budget exhausted: leave the loop and
            # return outside the handler. Returning a value from inside the
            # except handler trips coder.logging.coach-silent-swallow.
            break

    return None


def _persona_materialised(
    runtime_root: Path, persona: str, issue: int
) -> bool:
    """True when the spawn actually put the persona on disk.

    A complete ``cmd_spawn`` writes ``manifest.json`` into
    ``<runtime_root>/agents/<persona>-<issue>-<suffix>/``. A truthy
    ``cmd_spawn`` return whose persona left no such dir is an incomplete
    spawn (#733): ``_spawn_with_retries`` treats only a raised exception as
    failure, so without this check an empty spawn slips through to HANDLED
    and the coach stalls forever on a done.json no persona exists to write.
    """
    agents_dir = runtime_root / "agents"
    if not agents_dir.is_dir():
        return False
    prefix = f"{persona}-{issue}-"
    for entry in agents_dir.iterdir():
        if not entry.is_dir():
            continue
        if not entry.name.startswith(prefix) or entry.name.endswith("-observer"):
            continue
        if (entry / "manifest.json").is_file():
            return True
    return False


def _escalate(ctx: CoachContext, reason: str) -> None:
    if ctx.escalation_channel:
        print(
            f"❌ ESCALATE via {ctx.escalation_channel!r}: {reason}",
            file=sys.stderr,
        )


def _spawn_observer(
    ctx: CoachContext,
    phase: str,
    worktree: Path,
    persona_agent_id: str,
    runtime_root: Path,
    persona_surface_ref: Optional[str] = None,
) -> None:
    """Launch the observer L1 sidecar as a headless background process (#736).

    The observer (`atdd observer run`) is a plain CLI script — it takes
    ``--agent-id`` / ``--runtime-dir`` / ``--worktree`` and writes
    ``agents/<id>/corrections.jsonl`` directly. It needs no terminal, so it
    runs detached with no multiplexer surface: each worker is one tab
    (persona only), not two (persona + ``:obs``).

    ``persona_surface_ref`` is accepted for call-site compatibility and
    unused — the headless observer is not attached to any surface.
    Observer is supplementary — callers must catch and warn on any exception.
    """
    import subprocess

    observer_agent_id = f"{persona_agent_id}-observer"
    observer_cmd = [
        "atdd", "observer", "run",
        "--agent-id", observer_agent_id,
        "--runtime-dir", str(runtime_root),
        "--worktree", str(worktree),
    ]
    subprocess.Popen(
        observer_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _write_cospawn_decision(
    ctx: CoachContext,
    phase: str,
    runtime_root: Path,
) -> None:
    """Append an observer co-spawn decision record to decisions.jsonl."""
    from datetime import datetime, timezone
    from atdd.coach.commands.durability import DecisionWriter

    writer = DecisionWriter(runtime_dir=runtime_root)
    now = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    writer.append({
        "decision_id": str(uuid.uuid4()),
        "timestamp": now,
        "coach_run_id": ctx.coach_run_id,
        "issue_number": ctx.issue_number,
        "decision_type": "co_spawn_observer",
        "inputs": {"phase": phase},
        "outcome": {"status": "SPAWNED"},
    })


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    """Spawn the appropriate persona agent for this phase transition.

    Returns NOOP for transitions not in the persona table (e.g. BLOCKED,
    REFACTOR→COMPLETE), HANDLED on successful spawn, ERROR if the prompt
    is missing or all spawn attempts fail.
    """
    key = (transition.src, transition.dst)
    persona = _TRANSITION_PERSONA.get(key)
    if persona is None:
        return HandlerResult.NOOP

    phase = _TRANSITION_PHASE[key]
    run_id = f"coach-run-{ctx.issue_number}-{uuid.uuid4().hex[:8]}"
    runtime_root = _RUNTIME_ROOT

    try:
        persona_prompt_content = _load_persona_prompt(persona, phase)
    except PromptNotFoundError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        msg = str(exc)
        print(f"❌ spawn handler: {msg}", file=sys.stderr)
        try:
            _write_blocked_decision(ctx, transition, msg, run_id, runtime_root)
        except Exception as write_exc:
            print(
                f"⚠ spawn handler: could not write BLOCKED decision: {write_exc}",
                file=sys.stderr,
            )
        return HandlerResult.ERROR

    if ctx.dry_run:
        print(
            f"[dry-run] would spawn {persona}/{phase} "
            f"for issue #{ctx.issue_number}"
        )
        return HandlerResult.HANDLED

    llm = _resolve_llm(ctx, persona)
    worktree = _resolve_worktree(ctx)
    base_agent_id = f"{persona}-{ctx.issue_number}-{uuid.uuid4().hex[:8]}"

    result = _spawn_with_retries(
        ctx, transition, persona, phase, llm,
        persona_prompt_content, worktree, base_agent_id, runtime_root,
    )

    if result is None:
        attempts = (ctx.max_retries or 0) + 1
        reason = (
            f"spawn failed after {attempts} attempt(s) for "
            f"#{ctx.issue_number} ({persona}/{phase})"
        )
        _escalate(ctx, reason)
        try:
            _write_blocked_decision(ctx, transition, reason, run_id, runtime_root)
        except Exception as write_exc:
            print(
                f"⚠ spawn handler: could not write BLOCKED decision: {write_exc}",
                file=sys.stderr,
            )
        return HandlerResult.ERROR

    # E003 (#733): a truthy _spawn_with_retries result is not proof the
    # persona materialised — cmd_spawn could have returned without writing a
    # manifest / agent_spawned event. Verify the persona is actually on disk;
    # if not, BLOCK + escalate loudly instead of returning HANDLED and
    # leaving the coach stalled on a done.json no persona exists to write.
    if not _persona_materialised(runtime_root, persona, ctx.issue_number):
        reason = (
            f"persona spawn for #{ctx.issue_number} ({persona}/{phase}) "
            f"returned but did not materialise — no agent runtime dir / "
            f"manifest under {runtime_root}/agents/"
        )
        _escalate(ctx, reason)
        try:
            _write_blocked_decision(ctx, transition, reason, run_id, runtime_root)
        except Exception as write_exc:
            print(
                f"⚠ spawn handler: could not write BLOCKED decision: {write_exc}",
                file=sys.stderr,
            )
        return HandlerResult.ERROR

    try:
        persona_surface_ref = result.get("surface_ref") if result else None
        # Issue #730: remember the issue's persistent surface so the next
        # phase transition respawns the persona agent in place rather than
        # creating a new pane. The ctx is per-issue, so this ref survives
        # across every phase of the issue's lifecycle.
        if persona_surface_ref is not None:
            ctx.issue_surface_ref = persona_surface_ref
        # In pane mode, the multiplexer backend's `new_persona_surface` (called
        # by cmd_spawn) already co-spawns the observer as a tab in the persona's
        # pane. Calling _spawn_observer here would create a SECOND observer,
        # causing the over-spawn bug (#695). Skip in pane mode.
        if ctx.multiplexer_mode != "pane":
            _spawn_observer(ctx, phase, worktree, base_agent_id, runtime_root, persona_surface_ref=persona_surface_ref)
        try:
            _write_cospawn_decision(ctx, phase, runtime_root)
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass
    except Exception as obs_exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"⚠ spawn handler: observer co-spawn failed for "
            f"#{ctx.issue_number} ({phase}): {obs_exc}",
            file=sys.stderr,
        )

    return HandlerResult.HANDLED
