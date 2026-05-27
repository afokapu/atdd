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
- Per-LLM convention file generation: CLAUDE.md / CONDUCTOR.md / GLM.md /
  GEMINI.md (#K4 + #P3).
- Codex / gemini / glm adapter implementations (separate K-track).
- Coach-state-machine integration (#496 + #J4).
- Worktree creation (#J4 — K1 assumes ``--worktree`` exists).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional

from atdd.coach.utils.session_naming import (
    compute_issue_surface_name,
    compute_phase_surface_name,
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

# E014: forbidden flags that must never appear in a spawn command (#657).
_FORBIDDEN_SPAWN_FLAGS = ("--dangerously-skip-permissions",)


class SpawnPermissionViolation(ValueError):
    """Raised when a spawn adapter command contains a forbidden permission flag.

    E014: minimize agent-spawn-commands-containing-dangerously-skip-permissions (#657).
    """


def _assert_no_forbidden_flags(command: str) -> None:
    """Raise SpawnPermissionViolation if command contains any forbidden flag."""
    for flag in _FORBIDDEN_SPAWN_FLAGS:
        if flag in command:
            raise SpawnPermissionViolation(
                f"Forbidden flag detected in spawn command: {flag!r}. "
                "Use '--permission-mode acceptEdits --allowedTools ...' instead. "
                "See spawn.py permission policy doc. (#657)"
            )


# ---------------------------------------------------------------------------
# Adapter registry — open extension point per acceptance E001-UNIT-002
# ---------------------------------------------------------------------------


class AdapterError(RuntimeError):
    """Raised by _require_env when a required env var is absent."""


# ---------------------------------------------------------------------------
# E010 (#795): Worker launch-prompt readiness gate
# E011 (#799): Verify-or-fail-loud for every spawn pipeline stage
# ---------------------------------------------------------------------------


class WorkerReadinessTimeout(RuntimeError):
    """Raised by _wait_for_claude_ready when the worker never comes up within
    the bounded timeout. Message contains the surface ref, project key, and
    elapsed time for operator diagnostics."""


class RenameNotAccepted(WorkerReadinessTimeout):
    """Raised when /rename was sent but the canonical name never appeared in
    capture_pane_text within the bounded timeout (E011, issue #799)."""


class PasteDidNotLand(WorkerReadinessTimeout):
    """Raised when paste_text was called but the paste indicator or prompt
    prefix never appeared in capture_pane_text within the bounded timeout
    (E011, issue #799)."""


class PromptNotSubmitted(WorkerReadinessTimeout):
    """Raised when send_key(Enter) was called but no thinking/tool-use marker
    appeared in capture_pane_text within the bounded timeout. Indicates the
    swallowed-Enter failure mode (E011, issue #799)."""


class ProcessNotAlive(WorkerReadinessTimeout):
    """Raised by _verify_process_alive when the spawned shim process has already
    exited before the process-alive stage timeout, or when cli-return mode is
    active and agents/<id>/output.log never received a heartbeat byte (E018, #857)."""


class DeprecatedMultiplexerModeError(ValueError):
    """Raised when _create_surface is called with a cmux-deprecated mode.

    cmux >=0.64.7 rejects ``new-workspace`` and ``new-pane`` RPCs with
    ``Broken pipe (errno 32)``. Use ``mode='surface'`` (issue #830).
    """


def _verify_stage(
    stage_name: str,
    surface_ref: str,
    backend: Any,
    expect_any: tuple[str, ...],
    *,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.25,
) -> None:
    """Poll capture_pane_text until any expected signal appears or the timeout expires.

    Each spawn pipeline stage calls this after firing its cmux command to
    verify the expected post-condition. On timeout, raises a stage-specific
    subclass of WorkerReadinessTimeout that includes the stage name and
    surface ref in the message so callers can log exactly which stage failed.

    Stage-to-exception map (E011, issue #799):
      - "rename-accepted"  → RenameNotAccepted
      - "paste-landed"     → PasteDidNotLand
      - "prompt-submitted" → PromptNotSubmitted
      - (any other name)   → WorkerReadinessTimeout
    """
    if not hasattr(backend, "capture_pane_text"):
        return  # backend doesn't support pane capture; skip verification

    _STAGE_EXCEPTIONS: dict[str, type[WorkerReadinessTimeout]] = {
        "rename-accepted": RenameNotAccepted,
        "paste-landed": PasteDidNotLand,
        "prompt-submitted": PromptNotSubmitted,
    }
    exc_class = _STAGE_EXCEPTIONS.get(stage_name, WorkerReadinessTimeout)

    deadline = time.monotonic() + timeout_s
    start = time.monotonic()

    while time.monotonic() < deadline:
        try:
            text = backend.capture_pane_text(surface_ref)
        except Exception:
            time.sleep(poll_interval_s)
            continue

        if any(signal in text for signal in expect_any):
            return

        time.sleep(poll_interval_s)

    elapsed = time.monotonic() - start
    raise exc_class(
        f"Stage {stage_name!r} on {surface_ref!r} timed out after {timeout_s:.1f}s "
        f"(elapsed {elapsed:.1f}s): none of {expect_any!r} appeared in pane capture. "
        f"({SPAWN_RULE_ID})"
    )


def _verify_process_alive(
    proc: Any,
    agent_id: str,
    runtime_dir: Path,
    transport: str,
    *,
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.1,
) -> None:
    """Assert the shim process is still running after surface creation (E018, #857).

    Two-part check:
    1. proc.poll() must return None (process has not exited).
    2. In cli-return mode only: agents/<id>/output.log must contain at least
       1 byte within *timeout_s* — proof that the shim got past Popen and is
       tee-ing the pty output. A crashed shim leaves surface artifacts intact
       (rename, layout, tab title) but never writes output.log.

    Raises ProcessNotAlive on any failure so callers can escalate rather than
    proceeding to agent_spawned with a dead worker.
    """
    if proc is not None:
        rc = proc.poll()
        if rc is not None:
            raise ProcessNotAlive(
                f"Shim process for {agent_id!r} exited with code {rc} before "
                f"process-alive stage completed. ({SPAWN_RULE_ID})"
            )

    if transport != "cli-return":
        return

    output_log = runtime_dir / "output.log"
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if output_log.exists() and output_log.stat().st_size > 0:
            return
        if proc is not None and proc.poll() is not None:
            rc = proc.poll()
            raise ProcessNotAlive(
                f"Shim process for {agent_id!r} exited with code {rc} while "
                f"waiting for output.log heartbeat. ({SPAWN_RULE_ID})"
            )
        time.sleep(poll_interval_s)

    bleed_candidate = (
        Path.cwd() / ".atdd" / "runtime" / "agents" / agent_id / "output.log"
    )
    if bleed_candidate.exists() and bleed_candidate.stat().st_size > 0:
        raise ProcessNotAlive(
            f"Shim process for {agent_id!r} path-mismatch: "
            f"polled {output_log} but bleed candidate found at alternate path "
            f"{bleed_candidate} — shim wrote output to CWD-relative path instead of "
            f"the absolute runtime-dir. ({SPAWN_RULE_ID})"
        )
    raise ProcessNotAlive(
        f"Shim process for {agent_id!r} is alive but {output_log} never received "
        f"a heartbeat byte within {timeout_s:.1f}s — no bleed candidate found at alternate path. "
        f"({SPAWN_RULE_ID})"
    )


def _pre_trust_worktree(
    worktree_path: Path,
    claude_json_path: Optional[Path] = None,
) -> None:
    """Write a hasTrustDialogAccepted entry for *worktree_path* into
    ~/.claude.json before any surface is created.

    Claude Code only auto-skips the workspace-trust modal in -p/non-interactive
    mode. Every fresh interactive launch on an untrusted path shows the modal,
    which absorbs the /rename injection and the pasted launch prompt — the
    worker then shows "Press up to edit queued messages" with no processed
    content (#795). Writing the projects entry beforehand eliminates the modal
    for coach-created worktrees.

    Non-destructive: existing entries in ``~/.claude.json`` are preserved.
    Never raises (best-effort); callers continue even if the write fails.
    """
    if claude_json_path is None:
        env_override = os.environ.get("ATDD_CLAUDE_JSON_PATH")
        claude_json_path = Path(env_override) if env_override else Path.home() / ".claude.json"

    try:
        if claude_json_path.exists():
            existing = json.loads(claude_json_path.read_text())
        else:
            existing = {}

        projects: dict = existing.setdefault("projects", {})
        key = str(worktree_path.resolve())
        if key not in projects:
            projects[key] = {}
        projects[key]["hasTrustDialogAccepted"] = True

        claude_json_path.write_text(json.dumps(existing, indent=2))
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"⚠️  _pre_trust_worktree: could not write {claude_json_path}: {exc} "
            f"({SPAWN_RULE_ID})",
            file=sys.stderr,
        )


def _get_worker_ready_timeout(env=None) -> float:
    """Return the worker-ready timeout in seconds.

    Reads ATDD_WORKER_READY_TIMEOUT from *env* (or os.environ when None).
    Defaults to 30.0 — enough for cold-start worktrees that take 20-40s.
    """
    if env is None:
        env = os.environ
    raw = env.get("ATDD_WORKER_READY_TIMEOUT")
    if raw:
        return float(raw)
    return 30.0


def _wait_for_claude_ready(
    surface_ref: str,
    project_key: str,
    spawn_time: float,
    *,
    claude_projects_dir: Optional[Path] = None,
    multiplexer: Any = None,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.25,
    prompt_text: Optional[str] = None,
) -> None:
    """Poll until a Claude session .jsonl appears for *project_key*.

    The session file (named <uuid>.jsonl) is written by Claude Code at
    startup; its presence confirms the TUI has booted and is ready for
    input. Polling is bounded by *timeout_s*; exceeding it raises
    WorkerReadinessTimeout with full diagnostics (#795).

    ``spawn_time`` is retained in the signature for caller context (error
    messages). Files are accepted by existence, not mtime, because
    each worktree has a unique project-key path and _assert_worker_processing
    is the downstream gate that confirms the worker actually processed input.

    When *prompt_text* is given, this function also pastes the prompt,
    verifies each stage, and asserts the worker is processing — making the
    entire "ready-to-process" pipeline patchable as a single call.

    The env vars ATDD_WORKER_READY_TIMEOUT and ATDD_WORKER_POLL_INTERVAL
    override the defaults so tests can run with tight timings.
    """
    env_timeout = os.environ.get("ATDD_WORKER_READY_TIMEOUT")
    if env_timeout:
        timeout_s = float(env_timeout)
    env_poll = os.environ.get("ATDD_WORKER_POLL_INTERVAL")
    if env_poll:
        poll_interval_s = float(env_poll)

    if claude_projects_dir is None:
        env_override = os.environ.get("ATDD_CLAUDE_PROJECTS_DIR")
        claude_projects_dir = (
            Path(env_override) if env_override
            else Path.home() / ".claude" / "projects"
        )

    project_dir = claude_projects_dir / project_key
    deadline = time.monotonic() + timeout_s
    start = time.monotonic()

    while time.monotonic() < deadline:
        if project_dir.is_dir():
            for entry in project_dir.iterdir():
                if entry.suffix == ".jsonl":
                    break  # session file found — Claude has booted
            else:
                time.sleep(poll_interval_s)
                continue
            break
        time.sleep(poll_interval_s)
    else:
        elapsed = time.monotonic() - start
        raise WorkerReadinessTimeout(
            f"Worker on {surface_ref!r} did not boot within {timeout_s:.1f}s "
            f"(elapsed {elapsed:.1f}s). No session .jsonl found under "
            f"{project_dir}. project_key={project_key!r}. "
            f"({SPAWN_RULE_ID})"
        )

    if prompt_text is None:
        return

    # Paste the launch prompt and verify the full ready-to-process pipeline.
    try:
        multiplexer.paste_text(surface_ref, prompt_text)
        multiplexer.send_key(surface_ref, "Enter")
    except (MultiplexerError, OSError, AttributeError) as exc:
        print(
            f"⚠️  launch-prompt injection failed for {surface_ref}: {exc} "
            f"({SPAWN_RULE_ID})",
            file=sys.stderr,
        )

    _stage_timeout = timeout_s
    _stage_poll = poll_interval_s
    _verify_stage(
        stage_name="paste-landed",
        surface_ref=surface_ref,
        backend=multiplexer,
        expect_any=("paste again to expand", "1 file"),
        timeout_s=_stage_timeout,
        poll_interval_s=_stage_poll,
    )
    _verify_stage(
        stage_name="prompt-submitted",
        surface_ref=surface_ref,
        backend=multiplexer,
        expect_any=("⏺ Thinking", "⏺⏺", "esc to interrupt"),
        timeout_s=_stage_timeout,
        poll_interval_s=_stage_poll,
    )

    _assert_worker_processing(
        surface_ref=surface_ref,
        project_key=project_key,
        claude_projects_dir=claude_projects_dir,
    )


def _assert_worker_processing(
    surface_ref: str,
    project_key: str,
    *,
    claude_projects_dir: Optional[Path] = None,
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.25,
) -> None:
    """Assert the spawned worker is actively processing after prompt paste.

    Polls the session .jsonl byte size until it grows (proves Claude appended
    at least one new message after the launch prompt was pasted). A timeout
    raises WorkerReadinessTimeout so the caller can escalate instead of
    logging a phantom phase transition (#795, #797).

    Uses the same session file that _wait_for_claude_ready already confirmed
    exists — no multiplexer capture needed, so every backend is supported.
    """
    env_timeout = os.environ.get("ATDD_WORKER_READY_TIMEOUT")
    if env_timeout:
        timeout_s = float(env_timeout)
    env_poll = os.environ.get("ATDD_WORKER_POLL_INTERVAL")
    if env_poll:
        poll_interval_s = float(env_poll)

    if claude_projects_dir is None:
        env_override = os.environ.get("ATDD_CLAUDE_PROJECTS_DIR")
        claude_projects_dir = (
            Path(env_override) if env_override
            else Path.home() / ".claude" / "projects"
        )

    project_dir = claude_projects_dir / project_key

    jsonl_path: Optional[Path] = None
    for entry in project_dir.iterdir():
        if entry.suffix == ".jsonl":
            jsonl_path = entry
            break

    if jsonl_path is None:
        raise WorkerReadinessTimeout(
            f"Worker on {surface_ref!r}: no session .jsonl found under "
            f"{project_dir} to track growth. project_key={project_key!r}. "
            f"({SPAWN_RULE_ID})"
        )

    initial_size = jsonl_path.stat().st_size
    deadline = time.monotonic() + timeout_s
    start = time.monotonic()

    while time.monotonic() < deadline:
        if jsonl_path.stat().st_size > initial_size:
            return  # Claude appended at least one new message
        time.sleep(poll_interval_s)

    elapsed = time.monotonic() - start
    raise WorkerReadinessTimeout(
        f"Worker on {surface_ref!r} did not begin processing within "
        f"{timeout_s:.1f}s (elapsed {elapsed:.1f}s) after launch prompt was pasted. "
        f"Session .jsonl at {jsonl_path} did not grow (size: {initial_size} bytes). "
        f"project_key={project_key!r}. ({SPAWN_RULE_ID})"
    )


@dataclass
class AdapterConfig:
    """Structured configuration for a per-LLM spawn adapter (E013, issue #829).

    Carries the three spawn-time fields needed for the freedom-with-a-leash model:
    - ``build_command``: callable that produces the shell command string given the
      rendered launch-prompt path (preserves backward-compat via ``__call__``).
    - ``permission_flags``: structured list of CLI flags that pre-grant the freedom
      set so modals never fire (e.g. ``["--permission-mode", "acceptEdits"]``).
    - ``allowed_tools``: structured list of tool names included in the allowlist
      (e.g. ``["Bash", "Edit", "Write", ...]``).
    - ``non_interactive_smoke``: optional callable that verifies no modal events
      fire on a synthetic workload (L001).
    """

    build_command: Callable[[Path], str]
    permission_flags: List[str]
    allowed_tools: List[str]
    non_interactive_smoke: Optional[Callable] = field(default=None)

    def __call__(self, prompt_path: Path) -> str:
        """Delegate to build_command for backward compat with call-site adapter(prompt_path)."""
        return self.build_command(prompt_path)


def _require_env(var_name: str, adapter_id: str) -> str:
    """Return the value of ``var_name`` or raise AdapterError.

    Callers: each non-default adapter calls this at the top of its body so
    a missing credential fails loudly before any multiplexer surface is
    created.
    """
    value = os.environ.get(var_name)
    if not value:
        raise AdapterError(f"{adapter_id}: missing ${var_name}")
    return value


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


def _claude_glm_adapter(prompt_path: Path) -> str:
    """Adapter for claude-glm via z.ai endpoint (requires Z_AI_API_KEY).

    Prompt is injected post-boot (same pattern as claude-code — the
    --model flag routes to z.ai's GLM-5.1 model via the Claude CLI's
    custom-endpoint support).
    """
    _ = prompt_path  # injected post-boot, not via argv
    _require_env("Z_AI_API_KEY", "claude-glm")
    allowed_tools = "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
    return (
        f'claude --model glm-5.1 --permission-mode acceptEdits '
        f'--allowedTools "{allowed_tools}"'
    )


def _claude_gpt_adapter(prompt_path: Path) -> str:
    """Adapter for claude-gpt via OpenRouter (requires OPENROUTER_API_KEY).

    Prompt is injected post-boot. The --model flag routes through the
    Claude CLI's OpenRouter endpoint to GPT-5.5.
    """
    _ = prompt_path  # injected post-boot, not via argv
    _require_env("OPENROUTER_API_KEY", "claude-gpt")
    allowed_tools = "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
    return (
        f'claude --model gpt-5.5 --permission-mode acceptEdits '
        f'--allowedTools "{allowed_tools}"'
    )


def _codex_adapter(prompt_path: Path) -> str:
    """Adapter for the OpenAI Codex CLI (requires OPENAI_API_KEY).

    Uses --prompt-file to consume the rendered launch prompt by path,
    consistent with gemini and avoiding shell-quoting edge cases with
    multi-line prompts.
    """
    _require_env("OPENAI_API_KEY", "codex")
    return f"codex exec --prompt-file {shlex.quote(str(prompt_path))}"


def _gemini_adapter(prompt_path: Path) -> str:
    """Adapter for the Google Gemini CLI (requires GOOGLE_API_KEY).

    Uses --prompt-file to consume the rendered launch prompt by path,
    consistent with codex.
    """
    _require_env("GOOGLE_API_KEY", "gemini")
    return f"gemini generate --prompt-file {shlex.quote(str(prompt_path))}"


_CLAUDE_PERMISSION_FLAGS = ["--permission-mode", "acceptEdits"]
_CLAUDE_ALLOWED_TOOLS = [
    "Bash", "Edit", "Write", "Read", "TodoWrite", "Glob", "Grep", "WebFetch",
]


def _claude_code_non_interactive_smoke() -> None:
    """L001-SMOKE-001: confirm the freedom-set flags suppress Bash permission modals.

    Spawns `claude --permission-mode acceptEdits --allowedTools Bash -p ...`
    and asserts none of the modal-class markers ('(1) Yes', 'Allow this', etc.)
    appear in the captured output within 30 s.

    Raises RuntimeError if claude is not on PATH or a modal marker is found.
    """
    import shutil
    import subprocess as _subprocess

    if not shutil.which("claude"):
        raise RuntimeError(
            "claude not found on PATH — cannot run non_interactive_smoke. "
            "Install Claude Code CLI first."
        )
    allowed_tools = " ".join(_CLAUDE_ALLOWED_TOOLS)
    cmd = [
        "claude",
        "--permission-mode", "acceptEdits",
        "--allowedTools", allowed_tools,
        "-p", "Bash('echo smoke-ok')",
    ]
    result = _subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    combined = result.stdout + result.stderr
    modal_markers = ["(1) Yes", "(2) No", "Allow this Bash command", "❯ 1."]
    for marker in modal_markers:
        if marker in combined:
            raise RuntimeError(
                f"L001-SMOKE-001: modal detected in claude output "
                f"(marker: {marker!r}). The freedom-set permission_flags are "
                f"not suppressing permission prompts.\nOutput:\n{combined[:500]}"
            )


# Open extension point — codex / gemini / glm follow-up issues register
# their adapters here without editing this module's CLI surface.
# E013 (#829): each entry carries structured permission_flags + allowed_tools
# so validators and the #824 shim can introspect the freedom set without
# re-parsing the shell command string.
ADAPTER_REGISTRY: dict[str, AdapterConfig] = {
    "claude-code": AdapterConfig(
        build_command=_claude_code_adapter,
        permission_flags=_CLAUDE_PERMISSION_FLAGS,
        allowed_tools=_CLAUDE_ALLOWED_TOOLS,
        non_interactive_smoke=_claude_code_non_interactive_smoke,
    ),
    "claude-glm": AdapterConfig(
        build_command=_claude_glm_adapter,
        permission_flags=_CLAUDE_PERMISSION_FLAGS,
        allowed_tools=_CLAUDE_ALLOWED_TOOLS,
    ),
    "claude-gpt": AdapterConfig(
        build_command=_claude_gpt_adapter,
        permission_flags=_CLAUDE_PERMISSION_FLAGS,
        allowed_tools=_CLAUDE_ALLOWED_TOOLS,
    ),
    "codex": AdapterConfig(
        build_command=_codex_adapter,
        permission_flags=["--full-auto"],
        allowed_tools=["Bash", "Edit", "Write", "Read"],
    ),
    "gemini": AdapterConfig(
        build_command=_gemini_adapter,
        permission_flags=["--yolo"],
        allowed_tools=["Bash", "Edit", "Write", "Read"],
    ),
}


def _inject_agent_env(
    command: str, agent_id: str
) -> tuple[dict[str, str], str]:
    """Return ``(env_overrides, command)`` for ATDD_AGENT_ID injection (#731 / #854).

    Shape A fix (#854): previously returned a shell-prefixed string
    ``ATDD_AGENT_ID=<id> <command>`` which broke ``subprocess.Popen`` when
    passed through atdd-shim's argv without ``shell=True``.  Now returns a
    typed ``(dict, str)`` tuple so callers choose the injection mechanism:

    - cli-return path: pass env_overrides via ``--env`` flags to atdd-shim
      (``_build_shim_command`` handles this).
    - shell/multiplexer path: reconstruct the ``KEY=value`` prefix from the
      dict and prepend it to command as before.
    """
    if not agent_id:
        return {}, command
    return {"ATDD_AGENT_ID": agent_id}, command


# ---------------------------------------------------------------------------
# E004 (#841): PersonaShim wiring helpers
# ---------------------------------------------------------------------------


def _correction_transport() -> str:
    """Return the active correction transport from the environment.

    Returns 'cli-return' when ATDD_CORRECTION_TRANSPORT=cli-return, else ''.
    """
    return os.environ.get("ATDD_CORRECTION_TRANSPORT", "").strip().lower()


def _build_shim_command(
    adapter_command: str,
    agent_id: str,
    runtime_root: Path,
    env_overrides: dict[str, str] | None = None,
) -> str:
    """Wrap adapter_command with the atdd-shim entry point.

    E017 fix (#857): uses module-invocation form (sys.executable -m atdd.coach.shim)
    instead of a bare 'atdd-shim' token so PATH resolution is eliminated entirely.
    On multi-install hosts (e.g. homebrew 3.81.1 + pipx 3.82.4) the bare token
    resolves to whichever installation $PATH finds first, which may be stale.
    The module form routes through the SAME Python that is running coach.

    Shape A fix (#854): env_overrides are passed via ``--env KEY=VALUE`` flags
    so atdd-shim can apply them via ``subprocess.Popen(env=...)`` rather than
    relying on shell-style ``KEY=value`` argv[0] prefixes which fail without
    ``shell=True``.

    Produces:
      <sys.executable> -m atdd.coach.shim --agent-id <id> --runtime-dir <path> [--env K=V ...] -- <adapter_command>
    """
    env_flags = ""
    if env_overrides:
        env_flags = "".join(
            f" --env {shlex.quote(f'{k}={v}')}" for k, v in env_overrides.items()
        )
    return (
        f"{shlex.quote(sys.executable)} -m atdd.coach.shim"
        f" --agent-id {shlex.quote(agent_id)}"
        f" --runtime-dir {shlex.quote(str(runtime_root.resolve()))}"
        f"{env_flags}"
        f" -- {adapter_command}"
    )


def _prime_cli_return_inbox(agent_dir: Path, prompt_text: str) -> None:
    """Write the launch prompt as the first cli-return.jsonl entry.

    Called by cmd_spawn BEFORE the surface is created so PersonaShim can
    deliver the prompt as the first agent turn via the pty — eliminating the
    post-boot paste_text + send_key path (E004 / #841).

    The entry is a minimal correction record: only correction_text is required
    by PersonaShim._process_cli_return_line().
    """
    agent_dir.mkdir(parents=True, exist_ok=True)
    cli_return_path = agent_dir / "cli-return.jsonl"
    record = {"correction_text": prompt_text}
    with cli_return_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Multiplexer resolution (split out so tests can inject a fake)
# ---------------------------------------------------------------------------


def _resolve_multiplexer(preferred: Optional[str] = None):
    """Resolve the multiplexer backend. Tests monkeypatch this to inject
    a fake; production calls ``get_multiplexer(preferred)``."""
    from atdd.coach.utils.multiplexer import get_multiplexer

    return get_multiplexer(preferred=preferred)


# ---------------------------------------------------------------------------
# Agent runtime-dir layout — single source of truth (#733)
#
# cmd_spawn provisions one dir per agent under <runtime_root>/agents/. Both
# the writer here and the spawn handler's materialisation guard
# (handlers/spawn.py::_persona_materialised, which delegates to
# persona_materialised below) depend on this layout — keeping the literals in
# one place means the two can never drift apart.
# ---------------------------------------------------------------------------

_AGENTS_SUBDIR = "agents"
_MANIFEST_FILENAME = "manifest.json"
_OBSERVER_SUFFIX = "-observer"


def _agent_runtime_dir(runtime_root: Path, agent_id: str) -> Path:
    """The runtime dir cmd_spawn provisions for one agent id."""
    return runtime_root / _AGENTS_SUBDIR / agent_id


def persona_materialised(runtime_root: Path, persona: str, issue: int) -> bool:
    """True when a completed ``cmd_spawn`` left a persona agent dir on disk.

    A complete spawn writes ``manifest.json`` into
    ``<runtime_root>/agents/<persona>-<issue>-<suffix>/``. The spawn handler
    calls this to reject an incomplete spawn that returned a truthy result
    without putting the persona on disk (#733) — observer dirs (``-observer``
    suffix) are excluded so an orphan observer can never satisfy the check.
    """
    agents_dir = runtime_root / _AGENTS_SUBDIR
    if not agents_dir.is_dir():
        return False
    prefix = f"{persona}-{issue}-"
    for entry in agents_dir.iterdir():
        if not entry.is_dir():
            continue
        if not entry.name.startswith(prefix) or entry.name.endswith(_OBSERVER_SUFFIX):
            continue
        if (entry / _MANIFEST_FILENAME).is_file():
            return True
    return False


def _write_manifest(
    runtime_root: Path, agent_id: str, persona: str, issue: int,
) -> None:
    """Write ``manifest.json`` to the agent's runtime dir so downstream
    guards can read the persona without parsing events.jsonl."""
    agent_dir = _agent_runtime_dir(runtime_root, agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest = agent_dir / _MANIFEST_FILENAME
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


def _render_agent_identity_block(agent_id: str) -> str:
    """Belt-and-braces (#731): state the agent's own ``agent_id`` in the
    launch prompt so a persona can fall back to ``--agent-id`` if the
    ``ATDD_AGENT_ID`` env var is ever missing."""
    return (
        "## Agent Identity\n\n"
        f"Your ATDD agent id is `{agent_id}`. The coach exports it as the "
        "`ATDD_AGENT_ID` environment variable in this session, so every "
        "`atdd agent <subcommand>` (`done`, `heartbeat`, `event`, `ask`, "
        "`escalate`, …) resolves it automatically. If `ATDD_AGENT_ID` is "
        f"ever unset, pass `--agent-id {agent_id}` explicitly."
    )


def _prime_inbox_with_launch_prompt(
    *,
    agent_id: str,
    prompt_text: str,
    agent_dir: Path,
) -> Path:
    """Write the launch prompt as the first cli-return.jsonl entry.

    Called before the shim spawns the agent CLI when
    ATDD_CORRECTION_TRANSPORT=cli-return. The shim drains this entry
    and delivers it to the agent's pty stdin as the first user turn,
    replacing the post-boot paste_text + send_key approach (#702/#824).
    """
    import json as _json
    cli_return = agent_dir / "cli-return.jsonl"
    cli_return.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "rule_id": "BOOTSTRAP-001",
        "correction_text": prompt_text,
        "severity": 0,
        "issued_at": None,
        "prompt": prompt_text,
    }
    with cli_return.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(record, sort_keys=True) + "\n")
    return cli_return


def _render_launch_prompt(
    issue: int,
    worktree: Path,
    *,
    phase: Optional[str] = None,
    rules: Optional[Iterable[Any]] = None,
    persona: str = "",
    agent_id: str = "",
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

    # E023: inject wagon-graph section before the Workflow section so the agent
    # has structural context before reading the workflow steps.  Graceful degrade
    # when _build_wagon_graph_section raises (unknown wagon, subprocess failure,
    # etc.) — the prompt is still written and dispatch continues.
    try:
        wagon_graph_section = _build_wagon_graph_section(context.wagon)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        wagon_graph_section = None
    if wagon_graph_section:
        marker = "\n## Workflow"
        if marker in rendered:
            idx = rendered.find(marker)
            pre = rendered[:idx].rstrip()
            rendered = pre + "\n\n" + wagon_graph_section.rstrip() + "\n" + rendered[idx:]
        else:
            rendered = rendered.rstrip() + "\n\n" + wagon_graph_section

    # Pre-inject architecture context (E003): splice wagon/train/WMBT section
    # before rule blocks so the agent has structural context from the start.
    arch_section = _build_arch_section(issue)
    if arch_section:
        rendered = rendered.rstrip() + "\n\n" + arch_section

    if rules is not None and phase is not None:
        rendered = _append_spawn_rule_blocks(rendered, rules=rules, coach_phase=phase, persona=persona)

    # #731 Phase 1 (belt-and-braces): state the agent's own agent_id so the
    # persona can fall back to --agent-id if ATDD_AGENT_ID is ever missing.
    if agent_id:
        rendered = rendered.rstrip() + "\n\n" + _render_agent_identity_block(agent_id) + "\n"

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


def _build_wagon_graph_section(wagon_slug: str, *, repo_root: Optional[Path] = None) -> Optional[str]:
    """Return the wagon-scoped launch-prompt section, or None on any failure.

    E023: called by _render_launch_prompt to inject wagon architecture context
    before the Workflow section.  Returns None when wagon_slug is empty or
    the wagon has no manifest; never raises.
    """
    try:
        from atdd.coach.commands.issue_graph import build_wagon_launch_prompt

        if not wagon_slug:
            return None
        return build_wagon_launch_prompt(wagon_slug, repo_root=repo_root)
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


def _resolve_spawn_pane(backend) -> str:
    """Return the canonical pane ref for surface-mode spawning (issue #830).

    Calls ``backend.resolve_focused_pane()`` — implemented on CmuxBackend
    via ``cmux list-panes`` to pick the focused pane. Falls back to
    ``"pane:1"`` so FakeMultiplexer stubs in tests that omit the method
    never raise AttributeError.
    """
    resolve = getattr(backend, "resolve_focused_pane", None)
    if resolve is not None:
        return resolve()
    return "pane:1"


def _create_surface(
    multiplexer,
    *,
    worktree: Path,
    command: str,
    name: str,
    mode: str = "surface",
) -> str:
    """Dispatch to the multiplexer using the canonical surface RPC (issue #830).

    ``mode`` controls the surface creation strategy:
    - ``"surface"`` (default) / ``"auto"`` — call ``new_surface_in_pane``
      with the focused pane resolved via ``resolve_focused_pane()``. This
      is the canonical cmux path (``cmux new-surface --pane <ref>``) that
      works on cmux >=0.64.7 and never calls the deprecated new-workspace
      or new-pane RPCs.
    - ``"workspace"`` — raises ``DeprecatedMultiplexerModeError``. cmux
      0.64.7 rejects ``new-workspace`` with Broken pipe (errno 32).
    - ``"pane"`` — raises ``DeprecatedMultiplexerModeError``. cmux 0.64.7
      rejects ``new-pane`` with Broken pipe (errno 32).
    """
    if mode == "workspace":
        raise DeprecatedMultiplexerModeError(
            "multiplexer-mode='workspace' calls cmux new-workspace which fails with "
            "Broken pipe on cmux >=0.64.7. Use mode='surface' (the default). "
            "See issue #830."
        )
    if mode == "pane":
        raise DeprecatedMultiplexerModeError(
            "multiplexer-mode='pane' calls cmux new-pane which fails with "
            "Broken pipe on cmux >=0.64.7. Use mode='surface' (the default). "
            "See issue #830."
        )
    # "surface" / "auto" — canonical path: new-surface inside the focused pane.
    pane_ref = _resolve_spawn_pane(multiplexer)
    return multiplexer.new_surface_in_pane(
        pane_ref=pane_ref,
        cwd=str(worktree),
        command=command,
        name=name,
    )


def _respawn_persona_in_surface(
    backend: Any, surface_ref: str, command: str,
) -> str:
    """Relaunch a persona agent inside an existing surface (issue #730).

    Issues an in-place respawn against the issue's persistent surface — a
    fresh process, NOT a ``/clear`` conversation reset (Decision #5) — so the
    new persona's system prompt, tool config, and cwd apply cleanly. Backends
    without respawn support leave the surface as-is. Returns ``surface_ref``.
    """
    respawn = getattr(backend, "respawn_pane", None) or getattr(
        backend, "respawn", None
    )
    if respawn is None:
        return surface_ref
    try:
        respawn(surface_ref, command=command)
    except NotImplementedError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-01
        # tmux/zellij have no respawn verb — leave the surface as-is.
        pass
    return surface_ref


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


def _launch_headless_observer(
    observer_agent_id: str, runtime_root: Path, worktree: Path,
) -> None:
    """Launch the per-worker observer as a detached headless background process.

    Issue #745: ``cmd_spawn`` previously co-spawned the observer as a visible
    ``<issue>:obs`` multiplexer surface via ``new_persona_surface``. The
    observer (``atdd observer run``) is a plain CLI script that writes
    ``agents/<id>/corrections.jsonl`` directly — it needs no terminal. It now
    runs detached with no surface, exactly as ``handlers/spawn.py::
    _spawn_observer`` already does (#736): each worker is one tab, not two.

    Best-effort: the observer is supplementary, so a launch failure is warned
    and swallowed — it must never fail the persona spawn.
    """
    import subprocess

    observer_cmd = [
        "atdd", "observer", "run",
        "--agent-id", observer_agent_id,
        "--runtime-dir", str(runtime_root),
        "--worktree", str(worktree),
    ]
    try:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            observer_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:  # noqa: BLE001 — observer is supplementary
        print(
            f"⚠️  headless observer launch failed for {observer_agent_id}: "
            f"{exc} ({SPAWN_RULE_ID})",
            file=sys.stderr,
        )


def _spawn_observer_if_configured(
    agent_id: str,
    runtime_root: Path,
    worktree: Path,
) -> None:
    """Launch a headless observer if one is configured.

    Currently a no-op: per-worker observers were removed in issue #754.
    Exists as a named hook so callers can monkeypatch it in tests.
    """
    return None


def _emit_agent_spawned_event(
    *,
    persona: str,
    llm: str,
    worktree: Path,
    issue: int,
    surface_ref: str,
    canonical_name: str,
    agent_id: str,
    runtime_root: Path,
    phase: Optional[str] = None,
    target_commit: Optional[str] = None,
    prior_attempt: Optional[str] = None,
    multiplexer_ref: Optional[str] = None,
) -> None:
    """Write the ``agent_spawned`` runtime event for this worker."""
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
    multiplexer_mode: str = "surface",
    existing_surface_ref: Optional[str] = None,
) -> dict:
    """Render the launch prompt, dispatch the multiplexer, run the
    per-LLM adapter, and emit the ``agent_spawned`` event.

    The coach hosts each issue in ONE persistent surface named ``ATDD<N>``
    (issue #730). When ``existing_surface_ref`` is given, the persona agent is
    relaunched IN PLACE in that surface instead of a new pane being created.

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
    runtime_root = Path(runtime_root).resolve()

    prompt_path = _render_launch_prompt(
        issue, worktree, phase=phase, rules=rules, persona=persona, agent_id=agent_id,
    )

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

    # E014: guard against forbidden permission flags before any dispatch (#657).
    _assert_no_forbidden_flags(command)

    # #731 Phase 1: export the canonical ATDD_AGENT_ID into the persona
    # process environment. Applied here — after the per-LLM adapter — so the
    # injection is adapter-agnostic: every adapter in ADAPTER_REGISTRY
    # (claude-code today; codex / gemini / glm later) inherits it for free.
    # Without this the spawned persona has no ATDD_AGENT_ID and every
    # `atdd agent` subcommand fails closed, stalling the coach.
    # #731 / #854 Shape A: _inject_agent_env returns (env_overrides, command).
    # - cli-return path: env_overrides passed via --env flags to atdd-shim
    # - shell/multiplexer path: reconstruct KEY=value prefix for shell dispatch
    env_overrides, command = _inject_agent_env(command, agent_id)

    # E004 (#841): when ATDD_CORRECTION_TRANSPORT=cli-return, wrap the adapter
    # command in PersonaShim and prime the inbox with the launch prompt BEFORE
    # the surface is created. The shim becomes the pane foreground process;
    # the adapter runs in the shim-owned pty; the launch prompt is delivered
    # via cli-return.jsonl instead of paste_text + send_key.
    agent_dir = _agent_runtime_dir(runtime_root, agent_id)
    using_cli_return = _correction_transport() == "cli-return"
    if using_cli_return:
        _prime_cli_return_inbox(agent_dir, prompt_path.read_text())
        command = _build_shim_command(command, agent_id, runtime_root, env_overrides=env_overrides)
    elif env_overrides:
        # Shell/multiplexer dispatch: reconstruct KEY=value prefix so the shell
        # that runs the surface command sets the env var for the adapter process.
        prefix = " ".join(
            f"{k}={shlex.quote(str(v))}" for k, v in env_overrides.items()
        )
        command = f"{prefix} {command}"

    from atdd.coach.utils.config import load_atdd_config

    repo_short = compute_repo_short_name(load_atdd_config(Path.cwd()))
    # Issue #730: the coach hosts each issue in ONE persistent surface named
    # ATDD<N> — issue identity, stable across every phase. No slug / persona /
    # phase segment; the pane *is* the issue's identity.
    canonical_name = compute_issue_surface_name(repo_short, int(issue))

    backend = multiplexer if multiplexer is not None else _resolve_multiplexer()

    # E010 (#795): pre-trust the worktree so the workspace-trust modal is
    # never shown on the first interactive Claude Code launch. Fresh worktrees
    # have no entry in ~/.claude.json and always trigger the modal, which
    # absorbs the /rename injection and the pasted launch prompt before the
    # worker can act on them. Writing the entry here eliminates the modal.
    _pre_trust_worktree(worktree)

    # Issue #754: per-worker observer removed — a single MultiAgentObserver
    # is started once by _execute_cold_start and watches all agent dirs.
    spawn_time = time.time()
    if existing_surface_ref is not None:
        # Issue #730: the issue already has its persistent surface — relaunch
        # the persona agent in place rather than spawning a new pane. No
        # canonical naming/layout pass is needed: the surface keeps the
        # ATDD<N> identity it was created with.
        surface_ref = _respawn_persona_in_surface(
            backend, existing_surface_ref, command,
        )
    else:
        # Issue #745: create the persona surface ONLY. Passing no observer_*
        # arguments routes _create_surface through the plain surface primitive
        # (new_surface) instead of new_persona_surface — so spawning an issue
        # is exactly one tab, not a persona + co-spawned `:obs` pair.
        surface_ref = _create_surface(
            backend,
            worktree=worktree,
            command=command,
            name=canonical_name,
            mode=multiplexer_mode,
        )

    # E006 (#733): gate everything downstream — observer co-spawn, the
    # agent_spawned event, the manifest — on confirmed persona
    # materialisation. A falsy surface_ref means the multiplexer never
    # produced a persona surface (whether freshly created or respawned in
    # place); raising here (instead of pressing on and returning a truthy
    # success dict) lets _spawn_with_retries surface it as a failure so the
    # coach BLOCKs and escalates, rather than leaving an orphan
    # observer-without-persona behind (observed live on #662).
    if not surface_ref:
        raise MultiplexerError(
            f"persona spawn for {agent_id!r} did not materialise a "
            f"multiplexer surface — aborting before the observer co-spawn "
            f"to prevent an orphan observer-without-persona (#733)"
        )

    if existing_surface_ref is None:
        # Transactional spawn (#655): the surface exists. If the canonical
        # naming/layout pass fails, close it before propagating so the failed
        # spawn attempt leaves no orphan pane.
        try:
            _verify_timeout = float(os.environ.get("ATDD_WORKER_READY_TIMEOUT", "10.0"))
            _verify_poll = float(os.environ.get("ATDD_WORKER_POLL_INTERVAL", "0.25"))
            apply_canonical_name_and_layout(
                backend=backend,
                ref=surface_ref,
                canonical_name=canonical_name,
                surface_count=1,
                verify_after_send=True,
                verify_timeout_s=_verify_timeout,
                verify_poll_s=_verify_poll,
            )
        except Exception:
            _close_surface_on_failure(backend, surface_ref)
            raise

    # Phase-qualified surface name (#746): rename the worker surface to
    # ATDD<N>·<PHASE>·<persona> on every transition so the operator can see
    # which phase/agent is live. The pane is still the issue's persistent
    # surface — only its label changes. Best-effort: a rename failure must
    # not abort the spawn.
    if phase and persona:
        phase_surface_name = compute_phase_surface_name(
            repo_short, int(issue), phase, persona,
        )
        try:
            backend.rename(surface_ref, phase_surface_name)
        except (MultiplexerError, OSError, AttributeError) as exc:
            print(
                f"⚠️  phase-qualified rename failed for {surface_ref}: {exc} "
                f"({SPAWN_RULE_ID})",
                file=sys.stderr,
            )

    # E018 (#857): verify the spawned process is alive after surface creation.
    # In cli-return mode, also wait for agents/<id>/output.log to receive at
    # least one heartbeat byte — proof the shim got past Popen and is running.
    # A shim that crashes silently leaves all surface artifacts intact (rename,
    # layout, tab title) but never writes output.log, so this is the only
    # reliable liveness signal available without a direct process object.
    process_alive_timeout = float(
        os.environ.get("ATDD_PROCESS_ALIVE_TIMEOUT", "5.0")
    )
    try:
        _verify_process_alive(
            proc=None,
            agent_id=agent_id,
            runtime_dir=agent_dir,
            transport=_correction_transport(),
            timeout_s=process_alive_timeout,
        )
    except ProcessNotAlive as exc:
        print(
            f"❌ spawned process for {agent_id!r} is not alive: {exc} "
            f"({SPAWN_RULE_ID})",
            file=sys.stderr,
        )
        _close_surface_on_failure(backend, surface_ref)
        raise

    # E010 (#795): wait for Claude's TUI to be ready before pasting.
    # E004 (#841): skip the paste path entirely when ATDD_CORRECTION_TRANSPORT=
    # cli-return — the shim delivers the launch prompt via cli-return.jsonl
    # (already primed above); paste_text + send_key must not fire.
    if not using_cli_return:
        from atdd.coach.utils.session_naming_apply import _claude_project_key

        project_key = _claude_project_key(worktree)
        try:
            # E010 (#795) + E011 (#799): wait for Claude's TUI to boot, paste
            # the launch prompt, verify each readiness stage, and assert the
            # worker is processing. All post-creation checks are inside one
            # patchable call so unit tests cover this pipeline with one stub.
            _wait_for_claude_ready(
                surface_ref=surface_ref,
                project_key=project_key,
                spawn_time=spawn_time,
                multiplexer=backend,
                prompt_text=prompt_path.read_text(),
            )
        except WorkerReadinessTimeout as exc:
            print(
                f"❌ worker on {surface_ref!r} did not boot in time: {exc} "
                f"({SPAWN_RULE_ID})",
                file=sys.stderr,
            )
            _close_surface_on_failure(backend, surface_ref)
            raise

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

    _spawn_observer_if_configured(
        agent_id=agent_id,
        runtime_root=runtime_root,
        worktree=worktree,
    )

    _emit_agent_spawned_event(
        persona=persona,
        llm=llm,
        worktree=worktree,
        issue=issue,
        surface_ref=surface_ref,
        canonical_name=canonical_name,
        agent_id=agent_id,
        runtime_root=runtime_root,
        phase=phase,
        target_commit=target_commit,
        prior_attempt=prior_attempt,
        multiplexer_ref=multiplexer_ref,
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
