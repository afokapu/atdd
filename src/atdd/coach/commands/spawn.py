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
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from atdd.coach.utils.session_naming import (
    branch_to_slug,
    compute_canonical_name,
    compute_repo_short_name,
)
from atdd.coach.utils.session_naming_apply import (
    CANONICAL_SESSION_NAME_RULE_ID,
    apply_canonical_name_and_layout,
    capture_session_uuid,
)
from atdd.coach.utils.multiplexer import MultiplexerError

# Canonical rule-ID emitted on every spawn (spec §5.2 / §7.1). Observers
# bind on this anchor to correlate spawn-time decisions with downstream
# events. K-track follow-ups extend the namespace; the prefix is frozen.
SPAWN_RULE_ID = "coach.spawn.atdd-spawn-cli"

PERSONAS: tuple[str, ...] = ("planner", "tester", "coder", "reviewer")


# ---------------------------------------------------------------------------
# Adapter registry — open extension point per acceptance E001-UNIT-002
# ---------------------------------------------------------------------------


def _claude_code_adapter(prompt_path: Path) -> str:
    """Spec §5.2: shell out to ``claude`` to start an interactive session.

    The launch prompt is NOT passed as a positional argv element. Claude
    Code v2.1.x ignores a positional ``prompt`` argument in interactive
    mode (it is only consumed by ``-p/--print`` headless mode) — passing
    it produced an idle session with no task (#702). The prompt is instead
    injected post-boot by ``cmd_spawn`` via ``backend.paste_text`` +
    ``send_key("Enter")``. ``prompt_path`` is retained in the signature for
    adapter-registry uniformity.

    Permission policy: ``--permission-mode acceptEdits --allowedTools
    "Bash Edit Write Read TodoWrite Glob Grep WebFetch"`` is the sanctioned
    alternative to the forbidden ``bypassPermissions`` (per repo memory
    rule). Tool-level allowlist gives autonomous flow without skipping
    the permission system entirely.
    """
    _ = prompt_path  # injected post-boot, not via argv — see docstring
    allowed_tools = "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
    return (
        f'claude --permission-mode acceptEdits '
        f'--allowedTools "{allowed_tools}"'
    )


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


def _write_manifest(
    runtime_root: Path, agent_id: str, persona: str, issue: int,
) -> None:
    """Write ``manifest.json`` to the agent's runtime dir so downstream
    guards can read the persona without parsing events.jsonl."""
    agent_dir = runtime_root / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / "manifest.json"
    tmp = manifest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "persona": persona,
        "agent_id": agent_id,
        "issue": issue,
    }, sort_keys=True))
    tmp.replace(manifest)


# ---------------------------------------------------------------------------
# Core spawn flow
# ---------------------------------------------------------------------------


def _render_launch_prompt(
    issue: int,
    worktree: Path,
    *,
    phase: Optional[str] = None,
    rules: Optional[Iterable[Any]] = None,
    persona: str = "",
) -> Path:
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

    # Pre-inject architecture context (E003): splice wagon/train/WMBT section
    # before rule blocks so the agent has structural context from the start.
    arch_section = _build_arch_section(issue)
    if arch_section:
        rendered = rendered.rstrip() + "\n\n" + arch_section

    if rules is not None and phase is not None:
        rendered = _append_spawn_rule_blocks(rendered, rules=rules, coach_phase=phase, persona=persona)
    prompt_path = worktree / ".launch_prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(rendered)
    return prompt_path


def _build_arch_section(issue: int) -> Optional[str]:
    """Return the Architecture context markdown section, or None on any failure."""
    try:
        from atdd.coach.commands.issue_graph import build_issue_architecture_context

        return build_issue_architecture_context(issue)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def _append_spawn_rule_blocks(
    rendered: str, *, rules: Iterable[Any], coach_phase: str, persona: str = ""
) -> str:
    import yaml

    from atdd.coach.commands.spawn_harness_blocks import (
        render_security_rules_block,
        render_train_rules_block,
        render_wmbt_rules_block,
    )

    blocks: dict[str, list[dict[str, Any]]] = {}
    wmbt_rules = render_wmbt_rules_block(rules, coach_phase=coach_phase, persona=persona)
    if wmbt_rules:
        blocks["wmbt_rules"] = wmbt_rules
    train_rules = render_train_rules_block(rules, coach_phase=coach_phase, persona=persona)
    if train_rules:
        blocks["train_rules"] = train_rules
    security_rules = render_security_rules_block(rules, coach_phase=coach_phase, persona=persona)
    if security_rules:
        blocks["security_rules"] = security_rules
    if not blocks:
        return rendered
    return rendered.rstrip() + "\n\n" + yaml.safe_dump(blocks, sort_keys=False)


def _create_surface(
    multiplexer,
    *,
    worktree: Path,
    command: str,
    name: str,
    mode: str = "auto",
    observer_agent_id: Optional[str] = None,
    observer_name: Optional[str] = None,
    observer_command: Optional[str] = None,
    observer_runtime_root: Optional[str] = None,
) -> str:
    """Dispatch to the multiplexer.

    ``mode`` controls the surface creation strategy:
    - ``"pane"`` — call ``new_persona_surface`` (co-spawns observer; never
      falls back to workspace).
    - ``"workspace"`` — call ``new_workspace`` (no observer in workspace mode;
      observer-as-workspace is handled separately per #658 design).
    - ``"auto"`` (default) — try ``new_persona_surface``; fall back to
      ``new_workspace`` for tmux/zellij backends that raise
      ``NotImplementedError`` on ``new_surface``.
    """
    if mode == "workspace":
        return multiplexer.new_workspace(cwd=str(worktree), command=command, name=name)

    def _pane_spawn() -> str:
        if observer_agent_id is not None:
            return multiplexer.new_persona_surface(
                cwd=str(worktree),
                command=command,
                name=name,
                observer_runtime_root=observer_runtime_root or "",
                observer_agent_id=observer_agent_id,
                observer_name=observer_name or "",
                observer_command=observer_command or "",
            )
        return multiplexer.new_surface(cwd=str(worktree), command=command, name=name)

    if mode == "pane":
        return _pane_spawn()

    # "auto" — try pane spawn; fall back to new_workspace for tmux/zellij.
    try:
        return _pane_spawn()
    except NotImplementedError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        # Documented fallback per utils/multiplexer.py: tmux/zellij
        # backends raise NotImplementedError on new_surface; we degrade
        # to new_workspace so spawn works on every backend the
        # abstraction supports.
        return multiplexer.new_workspace(
            cwd=str(worktree), command=command, name=name,
        )


def _close_surface_on_failure(backend: Any, surface_ref: str) -> None:
    """Close a half-spawned surface so a failed spawn leaves no orphan pane (#655).

    Never raises: cleanup must not mask the original spawn error.
    """
    close = getattr(backend, "close", None)
    if close is None or not surface_ref:
        return
    try:
        close(surface_ref)
    except Exception as exc:  # noqa: BLE001 — cleanup must not mask the real error
        print(
            f"⚠️  orphan-pane cleanup could not close {surface_ref}: {exc} "
            f"({SPAWN_RULE_ID})",
            file=sys.stderr,
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
    rules: Optional[Iterable[Any]] = None,
    persona_prompt_content: Optional[str] = None,
    multiplexer_mode: str = "auto",
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

    prompt_path = _render_launch_prompt(issue, worktree, phase=phase, rules=rules, persona=persona)

    # Reviewer persona: layer the no-write adapter over the base prompt
    if persona == "reviewer":
        from atdd.coach.spawn.reviewer_adapter import render_reviewer_launch_prompt

        base = prompt_path.read_text()
        reviewer_prompt = render_reviewer_launch_prompt(
            base, target_commit=target_commit,
        )
        prompt_path.write_text(reviewer_prompt)

    # Persona prompt injection: append per-phase instructions before dispatch.
    # Must happen after the reviewer adapter (which also post-processes the prompt)
    # and before the adapter generates the command string, so the shell cat picks
    # up the enriched file at execution time.
    if persona_prompt_content:
        base = prompt_path.read_text()
        prompt_path.write_text(
            base.rstrip() + "\n\n# Persona instructions\n\n" + persona_prompt_content
        )

    adapter = ADAPTER_REGISTRY[llm]
    command = adapter(prompt_path)

    from atdd.coach.utils.config import load_atdd_config

    repo_short = compute_repo_short_name(load_atdd_config(Path.cwd()))
    slug = branch_to_slug(worktree.name) or worktree.name or agent_id
    canonical_name = compute_canonical_name(repo_short, int(issue), slug)

    backend = multiplexer if multiplexer is not None else _resolve_multiplexer()
    _observer_agent_id = f"{agent_id}-observer"
    # Canonical observer naming: <persona-canonical-name>:obs — makes the link
    # to its persona unmistakable in cmux/tmux/zellij tab/window lists.
    # Sort-adjacent + ':obs' suffix is multiplexer-agnostic (#695).
    _observer_name = f"{canonical_name}:obs"
    _observer_command = (
        f"atdd observer run"
        f" --agent-id {_observer_agent_id}"
        f" --runtime-dir {runtime_root}"
        f" --worktree {worktree}"
    )
    surface_ref = _create_surface(
        backend,
        worktree=worktree,
        command=command,
        name=canonical_name,
        mode=multiplexer_mode,
        observer_agent_id=_observer_agent_id,
        observer_name=_observer_name,
        observer_command=_observer_command,
        observer_runtime_root=str(runtime_root),
    )
    # Transactional spawn (#655): the surface exists. If the canonical
    # naming/layout pass fails, close it before propagating so the failed
    # spawn attempt leaves no orphan pane.
    try:
        apply_canonical_name_and_layout(
            backend=backend,
            ref=surface_ref,
            canonical_name=canonical_name,
            surface_count=1,
        )
    except Exception:
        _close_surface_on_failure(backend, surface_ref)
        raise

    # Inject the launch prompt as the first interactive message (#702).
    # Claude Code v2.1.x ignores a positional prompt arg in interactive
    # mode, so the prompt — rendered to <worktree>/.launch_prompt.txt —
    # must be pasted post-boot. paste_text uses bracketed paste so the
    # multi-line prompt lands as ONE input block (newlines stay literal);
    # send_key submits it. The /rename injection inside
    # apply_canonical_name_and_layout ran immediately before and reaches
    # claude reliably, so the surface is ready for the paste.
    try:
        backend.paste_text(surface_ref, prompt_path.read_text())
        backend.send_key(surface_ref, "Enter")
    except (MultiplexerError, OSError, AttributeError) as exc:
        # AttributeError tolerates partial backends (test fakes) that do
        # not implement paste_text — mirrors apply_canonical_name_and_layout.
        print(
            f"⚠️  launch-prompt injection failed for {surface_ref}: {exc} "
            f"({SPAWN_RULE_ID})",
            file=sys.stderr,
        )

    capture_session_uuid(
        backend=backend,
        ref=surface_ref,
        issue=int(issue),
        agent_id=agent_id,
        canonical_name=canonical_name,
        persona=persona,
        phase=phase,
        runtime_root=runtime_root,
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
        "canonical_name": canonical_name,
        "canonical_rule_id": CANONICAL_SESSION_NAME_RULE_ID,
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

    # Write manifest.json so downstream guards (e.g., reviewer commit
    # rejection in agent.py) can read the persona without parsing events.
    _write_manifest(runtime_root, agent_id, persona, issue)

    return {
        "launch_prompt_path": prompt_path,
        "surface_ref": surface_ref,
        "command": command,
        "rule_id": SPAWN_RULE_ID,
        "canonical_name": canonical_name,
        "canonical_rule_id": CANONICAL_SESSION_NAME_RULE_ID,
    }


# ---------------------------------------------------------------------------
# argparse dispatcher (`atdd spawn ...`)
# ---------------------------------------------------------------------------


# Required-flag sets per invocation mode (issue #662). The default mode
# needs the full six-flag set; the --from-prompt-file convenience variant
# derives --persona / --llm / --agent-id / --runtime so only three flags
# (--from-prompt-file, --worktree, --issue) are required.
_FULL_REQUIRED = ("--persona", "--llm", "--worktree", "--issue", "--agent-id", "--runtime")
_FROM_PROMPT_FILE_REQUIRED = ("--worktree", "--issue")

# argparse dest names keyed by flag, for the conditional-required check.
_FLAG_DESTS = {
    "--persona": "persona",
    "--llm": "llm",
    "--worktree": "worktree",
    "--issue": "issue",
    "--agent-id": "agent_id",
    "--runtime": "runtime_root",
}


class _SpawnParser(argparse.ArgumentParser):
    """argparse parser with conditionally-required flags (issue #662).

    The six launch flags are declared ``required=False`` so the
    ``--from-prompt-file`` convenience variant can omit four of them. The
    required-flag set is enforced after parsing: the full six in default
    mode, only ``--worktree`` / ``--issue`` when ``--from-prompt-file`` is
    supplied. A missing flag still exits 2 via ``argparse.error``.
    """

    def parse_known_args(self, args=None, namespace=None):  # noqa: D102
        ns, extras = super().parse_known_args(args, namespace)
        if getattr(ns, "from_prompt_file", None) is not None:
            required = _FROM_PROMPT_FILE_REQUIRED
        else:
            required = _FULL_REQUIRED
        missing = [
            flag for flag in required if getattr(ns, _FLAG_DESTS[flag], None) is None
        ]
        if missing:
            self.error(
                "the following arguments are required: " + ", ".join(missing)
            )
        return ns, extras


def _build_parser() -> argparse.ArgumentParser:
    parser = _SpawnParser(
        prog="atdd spawn",
        description=(
            "Coach v9 K1 spawn skeleton. Single rule-IDed entry point "
            "for every persona launch — wraps session_template.render, "
            "dispatches the multiplexer, runs the per-LLM adapter, and "
            "emits an agent_spawned runtime event."
        ),
    )
    parser.add_argument(
        "--persona", choices=list(PERSONAS),
        help="Persona to launch.",
    )
    # --llm intentionally accepts arbitrary strings; adapter validation
    # is deferred to dispatch time so follow-up K-track issues can land
    # codex / gemini / glm adapters without editing this CLI surface.
    parser.add_argument(
        "--llm",
        help=(
            "LLM adapter id (claude-code shipped in K1; codex / gemini / "
            "glm registered as separate adapters in K-track follow-ups)."
        ),
    )
    parser.add_argument(
        "--worktree", type=Path,
        help="Path to the worktree (assumed to already exist; #J4 owns creation).",
    )
    parser.add_argument(
        "--issue", type=int,
        help="GitHub issue number being launched.",
    )
    parser.add_argument(
        "--agent-id", dest="agent_id",
        help="Unique agent id; targets .atdd/runtime/agents/<id>/.",
    )
    parser.add_argument(
        "--runtime", type=Path, dest="runtime_root",
        help="Path to the runtime root (writes events.jsonl beneath it).",
    )
    parser.add_argument(
        "--from-prompt-file", default=None, dest="from_prompt_file", type=Path,
        help=(
            "Path to a launch-prompt file. Convenience variant (#662): "
            "derives --persona / --llm / --agent-id / --runtime from "
            "wagon-manifest defaults so only --worktree and --issue are "
            "required, shrinking the ergonomic gap to the cwd-correct path."
        ),
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


# Wagon-manifest defaults for the --from-prompt-file convenience variant
# (#662). Defaults plus per-issue conventions fill the four omitted flags
# so the cwd-correct path needs only --from-prompt-file / --worktree /
# --issue. The launched surface's cwd still equals --worktree — the
# convenience flag never weakens the cwd guarantee.
_FROM_PROMPT_FILE_DEFAULTS = {"persona": "coder", "llm": "claude-code"}


def _apply_from_prompt_file_defaults(args: argparse.Namespace) -> None:
    """Fill --persona / --llm / --agent-id / --runtime for a 3-flag launch.

    Mutates ``args`` in place. ``--persona`` / ``--llm`` come from
    wagon-manifest defaults; ``--agent-id`` follows the canonical
    ``<persona>-<issue>-NNN`` convention; ``--runtime`` defaults to the
    worktree-local runtime root.
    """
    if args.persona is None:
        args.persona = _FROM_PROMPT_FILE_DEFAULTS["persona"]
    if args.llm is None:
        args.llm = _FROM_PROMPT_FILE_DEFAULTS["llm"]
    if args.agent_id is None:
        args.agent_id = f"{args.persona}-{args.issue}-001"
    if args.runtime_root is None:
        args.runtime_root = Path(args.worktree) / ".atdd" / "runtime"


def run(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    persona_prompt_content: Optional[str] = None
    if args.from_prompt_file is not None:
        _apply_from_prompt_file_defaults(args)
        try:
            persona_prompt_content = Path(args.from_prompt_file).read_text()
        except OSError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            print(f"❌ cannot read --from-prompt-file: {exc}", file=sys.stderr)
            return 2
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
            persona_prompt_content=persona_prompt_content,
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
