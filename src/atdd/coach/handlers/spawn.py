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
    )


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
    """Call ``_call_spawn`` up to ``max_retries + 1`` times with exponential backoff.

    Returns the result dict on success, or ``None`` after all attempts fail.
    Backoff: 1 s, 2 s, 4 s, … (doubles each retry).
    """
    max_retries = ctx.max_retries or 0
    delay = 1.0

    for attempt in range(max_retries + 1):
        if attempt > 0:
            time.sleep(delay)
            delay *= 2
        agent_id = f"{base_agent_id}-{attempt}" if attempt > 0 else base_agent_id
        try:
            return _call_spawn(
                ctx, persona, phase, llm,
                persona_prompt_content, worktree, agent_id, runtime_root,
            )
        except Exception as exc:
            print(
                f"⚠ spawn attempt {attempt + 1}/{max_retries + 1} failed for "
                f"#{ctx.issue_number} ({persona}/{phase}): {exc}",
                file=sys.stderr,
            )
    return None


def _escalate(ctx: CoachContext, reason: str) -> None:
    if ctx.escalation_channel:
        print(
            f"❌ ESCALATE via {ctx.escalation_channel!r}: {reason}",
            file=sys.stderr,
        )


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

    return HandlerResult.HANDLED
