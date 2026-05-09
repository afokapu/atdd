# URN: component:spawn-agents:atdd-spawn-skeleton-and-harness:spawn:application
# Runtime: python
# Purpose: Single rule-IDed entry point that wraps session_template.render, dispatches the multiplexer surface, runs the per-LLM adapter, and emits an agent_spawned runtime event (spec v9 §5.2 / §7.1).

"""`atdd spawn` — coach v9 K1 spawn skeleton (issue #499).

Single rule-IDed launch surface that every coach v9 persona launch
(planner / tester / coder / reviewer) flows through. K1 ships:

1. The CLI per spec §5.2 with the required flag set
   (``--persona``, ``--llm``, ``--worktree``, ``--issue``, ``--agent-id``,
   ``--runtime``, plus optional ``--phase``, ``--target-commit``,
   ``--prior-attempt``, ``--multiplexer-ref``).
2. A thin wrapper around ``session_template.render`` that writes
   ``<worktree>/.launch_prompt.txt``.
3. Multiplexer dispatch via the existing ``get_multiplexer`` abstraction
   (cmux / zellij / tmux backends).
4. A per-``--llm`` adapter registry; K1 ships ``claude-code``. Codex /
   gemini / glm land in K-track follow-ups by registering on the same
   registry without editing the CLI surface.
5. An ``agent_spawned`` runtime event written to
   ``<runtime>/agents/<agent_id>/events.jsonl`` conforming to
   ``runtime-event.schema.json`` (frozen at #483).

Out of scope (each owned by an adjacent K-track issue):
- Substrate spawn-harness blocks ``wmbt_rules`` / ``train_rules`` /
  ``security_rules`` (#K2).
- Canonical-naming + layout pass post-launch (#K3).
- Per-LLM convention file generation: CLAUDE.md / AGENTS.md / GLM.md /
  GEMINI.md (#K4 + #P3).
- Codex / gemini / glm adapter implementations (separate K-track).
- Coach-state-machine integration (#496 + #J4).
- Worktree creation (#J4 — K1 assumes ``--worktree`` exists).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# Canonical rule-ID emitted on every spawn (spec §5.2 / §7.1). Observers
# bind on this anchor to correlate spawn-time decisions with downstream
# events. K-track follow-ups extend the namespace; the prefix is frozen.
SPAWN_RULE_ID = "coach.spawn.atdd-spawn-cli"

PERSONAS: tuple[str, ...] = ("planner", "tester", "coder", "reviewer")


# ---------------------------------------------------------------------------
# Adapter registry — open extension point per acceptance E001-UNIT-002
# ---------------------------------------------------------------------------


def _claude_code_adapter(prompt_path: Path) -> str:
    """Spec §5.2: shell out to ``claude`` with the rendered launch prompt
    inlined via ``$(cat <prompt>)``. The shell expands the substitution
    inside the multiplexer surface so claude receives the full prompt as
    one argv element."""
    return f'claude --dangerously-skip-permissions "$(cat {prompt_path})"'


# Open extension point — codex / gemini / glm follow-up issues register
# their adapters here without editing this module's CLI surface.
ADAPTER_REGISTRY: dict[str, Callable[[Path], str]] = {
    "claude-code": _claude_code_adapter,
}


# ---------------------------------------------------------------------------
# Multiplexer resolution (split out so tests can inject a fake)
# ---------------------------------------------------------------------------


def _resolve_multiplexer(preferred: Optional[str] = None):
    """Resolve the multiplexer backend. Tests monkeypatch this to inject
    a fake; production calls ``get_multiplexer(preferred)``."""
    from atdd.coach.utils.multiplexer import get_multiplexer

    return get_multiplexer(preferred=preferred)


# ---------------------------------------------------------------------------
# Core spawn flow
# ---------------------------------------------------------------------------


def _render_launch_prompt(issue: int, worktree: Path) -> Path:
    """Wrap ``session_template`` to render the launch prompt and write
    it to ``<worktree>/.launch_prompt.txt``. Returns the prompt path."""
    from atdd.coach.commands import session_template

    fetched = session_template.fetch_issue(issue)
    body = (fetched or {}).get("body") or ""
    title = (fetched or {}).get("title") or ""
    context = session_template.build_context(
        issue_number=issue,
        body=body,
        title=title,
        worktree_path=str(worktree),
    )
    rendered = session_template.render(context)
    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(rendered)
    return prompt_path


def _create_surface(
    multiplexer,
    *,
    worktree: Path,
    command: str,
    name: str,
) -> str:
    """Dispatch to the multiplexer. Prefer ``new_surface`` (the cmux
    workspace+pane+surface model used by orchestrate); fall back to
    ``new_workspace`` for tmux / zellij backends per the abstraction
    contract in ``utils/multiplexer.py``."""
    try:
        return multiplexer.new_surface(
            cwd=str(worktree), command=command, name=name,
        )
    except NotImplementedError:
        return multiplexer.new_workspace(
            cwd=str(worktree), command=command, name=name,
        )


def cmd_spawn(
    *,
    persona: str,
    llm: str,
    worktree: Path,
    issue: int,
    agent_id: str,
    runtime_root: Path,
    phase: Optional[str] = None,
    target_commit: Optional[str] = None,
    prior_attempt: Optional[str] = None,
    multiplexer_ref: Optional[str] = None,
    multiplexer: Any = None,
) -> dict:
    """Render the launch prompt, dispatch the multiplexer, run the
    per-LLM adapter, and emit the ``agent_spawned`` event.

    Returns a dict with keys ``launch_prompt_path``, ``surface_ref``,
    ``command``, ``rule_id`` for callers that want to log or chain.
    """
    if persona not in PERSONAS:
        raise ValueError(
            f"persona {persona!r} not in {PERSONAS} — extend PERSONAS to add."
        )
    if llm not in ADAPTER_REGISTRY:
        registered = sorted(ADAPTER_REGISTRY.keys())
        raise ValueError(
            f"llm {llm!r} has no registered adapter. "
            f"Registered: {registered}. Add a new adapter to "
            f"ADAPTER_REGISTRY in spawn.py without editing the CLI surface."
        )

    worktree = Path(worktree)
    runtime_root = Path(runtime_root)

    prompt_path = _render_launch_prompt(issue, worktree)
    adapter = ADAPTER_REGISTRY[llm]
    command = adapter(prompt_path)

    backend = multiplexer if multiplexer is not None else _resolve_multiplexer()
    surface_ref = _create_surface(
        backend, worktree=worktree, command=command, name=agent_id,
    )

    # Emit agent_spawned event via the existing agent.cmd_event primitive
    # so the schema-conforming write path is shared with #J2 (#497).
    from atdd.coach.commands import agent as agent_mod

    payload: dict[str, Any] = {
        "persona": persona,
        "llm": llm,
        "worktree": str(worktree),
        "issue": int(issue),
        "surface_ref": surface_ref,
        "rule_id": SPAWN_RULE_ID,
    }
    if phase is not None:
        payload["phase"] = phase
    if target_commit is not None:
        payload["target_commit"] = target_commit
    if prior_attempt is not None:
        payload["prior_attempt"] = prior_attempt
    if multiplexer_ref is not None:
        payload["multiplexer_ref"] = multiplexer_ref

    agent_mod.cmd_event(
        "agent_spawned",
        agent_id=agent_id,
        data=payload,
        runtime_root=runtime_root,
    )

    return {
        "launch_prompt_path": prompt_path,
        "surface_ref": surface_ref,
        "command": command,
        "rule_id": SPAWN_RULE_ID,
    }


# ---------------------------------------------------------------------------
# argparse dispatcher (`atdd spawn ...`)
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd spawn",
        description=(
            "Coach v9 K1 spawn skeleton. Single rule-IDed entry point "
            "for every persona launch — wraps session_template.render, "
            "dispatches the multiplexer, runs the per-LLM adapter, and "
            "emits an agent_spawned runtime event."
        ),
    )
    parser.add_argument(
        "--persona", required=True, choices=list(PERSONAS),
        help="Persona to launch.",
    )
    # --llm intentionally accepts arbitrary strings; adapter validation
    # is deferred to dispatch time so follow-up K-track issues can land
    # codex / gemini / glm adapters without editing this CLI surface.
    parser.add_argument(
        "--llm", required=True,
        help=(
            "LLM adapter id (claude-code shipped in K1; codex / gemini / "
            "glm registered as separate adapters in K-track follow-ups)."
        ),
    )
    parser.add_argument(
        "--worktree", required=True, type=Path,
        help="Path to the worktree (assumed to already exist; #J4 owns creation).",
    )
    parser.add_argument(
        "--issue", required=True, type=int,
        help="GitHub issue number being launched.",
    )
    parser.add_argument(
        "--agent-id", required=True, dest="agent_id",
        help="Unique agent id; targets .atdd/runtime/agents/<id>/.",
    )
    parser.add_argument(
        "--runtime", required=True, type=Path, dest="runtime_root",
        help="Path to the runtime root (writes events.jsonl beneath it).",
    )
    parser.add_argument("--phase", default=None, help="Optional ATDD phase context.")
    parser.add_argument(
        "--target-commit", default=None, dest="target_commit",
        help="Optional reviewer/replay anchor (spec §6.3).",
    )
    parser.add_argument(
        "--prior-attempt", default=None, dest="prior_attempt",
        help="Optional prior-attempt agent_id for re-spawn correlation.",
    )
    parser.add_argument(
        "--multiplexer-ref", default=None, dest="multiplexer_ref",
        help="Optional existing workspace/pane ref (passes through to event payload).",
    )
    parser.add_argument(
        "--multiplexer", default=None,
        help="Optional multiplexer backend selection (cmux / zellij / tmux).",
    )
    return parser


def run(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = cmd_spawn(
            persona=args.persona,
            llm=args.llm,
            worktree=args.worktree,
            issue=args.issue,
            agent_id=args.agent_id,
            runtime_root=args.runtime_root,
            phase=args.phase,
            target_commit=args.target_commit,
            prior_attempt=args.prior_attempt,
            multiplexer_ref=args.multiplexer_ref,
            multiplexer=(
                _resolve_multiplexer(args.multiplexer)
                if args.multiplexer
                else None
            ),
        )
    except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(
        f"✓ spawned {args.agent_id} ({args.persona}/{args.llm}) "
        f"surface={result['surface_ref']} rule_id={result['rule_id']}"
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))
