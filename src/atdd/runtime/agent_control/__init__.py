"""``atdd.runtime.agent_control`` — the runtime agent-control layer (Child 6).

docs/coach-decomposition.md §4.8 / §13.6. Owns worker spawn (shim), prompt
delivery, ready detection, the correction inbox, stdin forwarding, agent done
signals, and transport selection. **cmux-native is the default launch plane**
(#978): cmux opens the surface running the agent and the agent's positional
prompt seeds AND auto-submits the first turn. ``ATDD_USE_LEGACY_SPAWN=1`` (the
kill switch) routes to the shim (cli-return / ``ShimAgentController``) — the
proven prior launch path, kept as the soak fallback until the shim is deleted
(#979). The screen-scrape (tui-scrape) path remains reachable only via an
explicit ``ATDD_CORRECTION_TRANSPORT=tui-scrape`` override. The shim default
closed the #840 / #871 / #872 cluster; cmux-native retires the cold-start
heartbeat flake and the #950 submit-sentinel bug from the launch path.

Dependency rule (§3.3): this layer imports stdlib (+ subprocess) only. It MUST
NOT import ``atdd.coach.*``, ``atdd.train.*``, ``atdd.integrations.*``, or
``atdd.runtime.multiplexer``. Consequently ``DispatchSpec.persona`` is typed
``str`` (it carries an ``atdd.coach.core.types.Persona`` value, which is a
``StrEnum`` — importing the enum here would violate the import-discipline gate).
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterator, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from atdd.runtime.agent_control._shim import PersonaShim

__all__ = [
    "DispatchSpec",
    "ReadyResult",
    "AgentEvent",
    "AgentSignal",
    "AgentHandle",
    "AgentController",
    "ShimAgentController",
    "TuiScrapeAgentController",
    "HeadlessPrintController",
    "CmuxAgentController",
    "PersonaShim",
    "resolve_transport",
    "DEFAULT_TRANSPORT",
    "SHIM_TRANSPORT",
    "LEGACY_TRANSPORT",
    "LEGACY_SPAWN_ENV",
    "ForbiddenLaunchFlagError",
    "assert_no_forbidden_launch_flags",
    "FORBIDDEN_LAUNCH_FLAGS",
]

_logger = logging.getLogger(__name__)

# --- forbidden-flag guard (E014, #969) -----------------------------------
#
# The cmux-surface adapter path is guarded by
# ``coach.commands.spawn._assert_no_forbidden_flags`` (which inspects the
# adapter command STRING). The cli-return / Shim launch transport builds its
# own argv list, which previously bypassed that guard entirely — which is why
# the contradictory ``--dangerously-skip-permissions`` config survived here
# (#967 root cause). This is the runtime-local, import-clean (§3.3 stdlib-only)
# twin: every launch path in this layer runs its argv through it.

FORBIDDEN_LAUNCH_FLAGS: tuple[str, ...] = ("--dangerously-skip-permissions",)


class ForbiddenLaunchFlagError(ValueError):
    """Raised when a launch argv carries a forbidden permission flag.

    E014 (#657 / #969): ``--dangerously-skip-permissions`` suppresses *all*
    ``PermissionRequest`` events, so escalation-worthy worker decisions never
    surface. The sanctioned freedom set is
    ``--permission-mode acceptEdits --allowedTools <scoped>`` (one policy,
    carried by ``DispatchSpec.permission_mode`` + ``allowed_tools``).
    """


def assert_no_forbidden_launch_flags(argv: Sequence[str]) -> None:
    """Raise ForbiddenLaunchFlagError if any argv token carries a forbidden flag.

    Substring match (mirrors the coach-side guard) so the ``--flag=value`` form
    is caught as well as the bare flag.
    """
    for token in argv:
        for flag in FORBIDDEN_LAUNCH_FLAGS:
            if flag in token:
                raise ForbiddenLaunchFlagError(
                    f"Forbidden launch flag detected in argv: {flag!r} (token {token!r}). "
                    "Use '--permission-mode acceptEdits --allowedTools ...' derived "
                    "from DispatchSpec instead — it surfaces decisions for "
                    "non-allowlisted tools. (E014, #969)"
                )

# --- transport selection -------------------------------------------------

DEFAULT_TRANSPORT = "cmux-native"
SHIM_TRANSPORT = "cli-return"
LEGACY_TRANSPORT = "tui-scrape"
LEGACY_SPAWN_ENV = "ATDD_USE_LEGACY_SPAWN"
_LEGACY_OVERRIDE_ENV = "ATDD_CORRECTION_TRANSPORT"  # back-compat explicit override

_TRUEY = {"1", "true", "yes", "on"}


def resolve_transport(env: Optional[Mapping[str, str]] = None) -> str:
    """Resolve the dispatch transport (§13.6, §12.4 R-4).

    Precedence (most-specific first):

    1. An explicit ``ATDD_CORRECTION_TRANSPORT`` value (forward opt-in / test
       override) wins — including ``cmux-native``, ``cli-return`` and the
       deprecated ``tui-scrape``.
    2. ``ATDD_USE_LEGACY_SPAWN=1`` (the kill switch) routes to the shim
       (``cli-return`` / ``ShimAgentController``) — the proven prior launch
       path kept as the soak fallback for #978.
    3. Otherwise ``cmux-native`` — the DEFAULT launch plane (#978): cmux opens
       the surface running the agent and the positional prompt seeds AND
       auto-submits the first turn (no pty shim, no cli-return inbox, no submit
       sentinel; decisions ride the cmux Feed hooks).
    """
    env = os.environ if env is None else env
    override = str(env.get(_LEGACY_OVERRIDE_ENV, "")).strip().lower()
    if override:
        return override
    if str(env.get(LEGACY_SPAWN_ENV, "")).strip().lower() in _TRUEY:
        return SHIM_TRANSPORT
    return DEFAULT_TRANSPORT


# --- typed contracts (§4.8) ---------------------------------------------


@dataclass(frozen=True)
class DispatchSpec:
    """Typed handoff between train runner (decided *what*) and runtime (*do it*).

    ``persona`` carries an ``atdd.coach.core.types.Persona`` value but is typed
    ``str`` to keep this layer import-clean of ``atdd.coach`` (§3.3).
    """

    agent_id: str
    persona: str
    worktree_path: Path
    prompt_text: str             # FULLY RENDERED — train runner did substitution
    correction_inbox: Path       # cli-return.jsonl
    output_log: Path
    runtime_dir: Path
    env_overrides: Mapping[str, str]
    transport: Literal["cli-return", "tui-scrape", "headless-print"]
    permission_mode: Literal["acceptEdits", "default", "plan"]
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True)
class ReadyResult:
    is_ready: bool
    transport_signal: str        # which signal fired (e.g. "output_log_heartbeat")
    elapsed_seconds: float


@dataclass(frozen=True)
class AgentEvent:
    type: Literal["thinking", "tool_use", "phase_complete", "agent_done", "error"]
    timestamp: str
    payload: dict


class AgentSignal(StrEnum):
    INTERRUPT = "interrupt"
    DONE_ACK = "done_ack"
    PROMPT_ADDITIONAL = "prompt_additional"


@dataclass(frozen=True)
class AgentHandle:
    """Opaque reference to a spawned agent (§4.7). Implementation-defined
    contents; live process state is held by the controller, keyed by agent_id."""

    agent_id: str
    spec: DispatchSpec
    spawned_at: str
    transport: Literal["cli-return", "tui-scrape", "headless-print", "cmux-native"]


@runtime_checkable
class AgentController(Protocol):
    def spawn(self, spec: DispatchSpec) -> AgentHandle: ...

    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:
        """Initial OR mid-run correction. Implementation MUST inject AND submit
        (closes #872 — submit gap)."""

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float) -> ReadyResult: ...

    def stream_events(self, handle: AgentHandle) -> Iterator[AgentEvent]: ...

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        """Including stdin forwarding for INTERRUPT (closes #871 — stdin gap)."""

    def stop(self, handle: AgentHandle, *, reason: str) -> None: ...


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _append_correction(inbox: Path, prompt: str) -> None:
    """Append one correction row to a cli-return.jsonl inbox (inject step).

    The submit step is performed by the shim drain (it always appends the submit
    sentinel) — together this closes #872.
    """
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"correction_text": prompt}) + "\n")


# --- ShimAgentController (default) ---------------------------------------


class ShimAgentController:
    """Default controller: pty shim + cli-return.jsonl priming + output.log
    heartbeat ready detection + structured event stream (§4.8).

    Live engines/threads are tracked here, keyed by ``agent_id``, so
    ``AgentHandle`` stays a clean frozen value object.
    """

    transport_name = "cli-return"

    def __init__(self, *, runtime_dir: Optional[Path] = None) -> None:
        self._runtime_dir = runtime_dir
        self._engines: dict[str, PersonaShim] = {}
        self._threads: dict[str, threading.Thread] = {}

    # -- preparation / dispatch-command construction ----------------------

    def prepare(self, spec: DispatchSpec) -> AgentHandle:
        """Return a handle for file-based delivery WITHOUT launching a process.

        Used by the production cmux path: the inbox is primed here, then the
        shim command (built via ``build_dispatch_command``) is run as the cmux
        surface foreground process.
        """
        spec.correction_inbox.parent.mkdir(parents=True, exist_ok=True)
        return AgentHandle(
            agent_id=spec.agent_id,
            spec=spec,
            spawned_at=_now_iso(),
            transport="cli-return",
        )

    def build_dispatch_command(
        self,
        adapter_command: str,
        *,
        agent_id: str,
        runtime_root: Path,
        env_overrides: Optional[Mapping[str, str]] = None,
    ) -> str:
        """Wrap an adapter command with the runtime agent-control shim entry point.

        Produces (module-invocation form so PATH resolution is eliminated, #857)::

          <python> -m atdd.runtime.agent_control --agent-id <id>
              --runtime-dir <path> [--env K=V ...] -- <adapter_command>
        """
        env_flags = ""
        if env_overrides:
            env_flags = "".join(
                f" --env {shlex.quote(f'{k}={v}')}" for k, v in env_overrides.items()
            )
        return (
            f"{shlex.quote(sys.executable)} -m atdd.runtime.agent_control"
            f" --agent-id {shlex.quote(agent_id)}"
            f" --runtime-dir {shlex.quote(str(Path(runtime_root).resolve()))}"
            f"{env_flags}"
            f" -- {adapter_command}"
        )

    # -- AgentController protocol -----------------------------------------

    def spawn(self, spec: DispatchSpec, *, agent_command: Optional[Sequence[str]] = None,
              timeout: Optional[float] = None) -> AgentHandle:
        """Launch the wrapped agent in a pty owned by this process (headless /
        test hosting). The production cmux path uses ``prepare`` +
        ``build_dispatch_command`` instead."""
        command = list(agent_command) if agent_command is not None else self._default_command(spec)
        # Close the E014 gap for caller-injected commands too (#969): the launch
        # boundary refuses a forbidden permission flag no matter who built argv.
        assert_no_forbidden_launch_flags(command)
        shim = PersonaShim(
            agent_id=spec.agent_id,
            spawn_command=command,
            runtime_dir=spec.runtime_dir,
            env_overrides=dict(spec.env_overrides),
        )
        thread = threading.Thread(
            target=shim.run, kwargs={"timeout": timeout}, daemon=True,
            name=f"agent-shim-{spec.agent_id}",
        )
        self._engines[spec.agent_id] = shim
        self._threads[spec.agent_id] = thread
        thread.start()
        # Wait briefly until the child process object is available so callers can
        # immediately interrogate liveness / signal it.
        deadline = time.monotonic() + 5.0
        while shim._proc is None and time.monotonic() < deadline:
            time.sleep(0.01)
        return AgentHandle(
            agent_id=spec.agent_id,
            spec=spec,
            spawned_at=_now_iso(),
            transport="cli-return",
        )

    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:
        """Inject AND submit a prompt (initial or mid-run) via cli-return.jsonl.

        The inbox write is the *inject*; the running shim drains the row and
        appends the submit sentinel — the *submit* (closes #872)."""
        _append_correction(handle.spec.correction_inbox, prompt)

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float) -> ReadyResult:
        """Ready when the agent's output.log has received ≥1 heartbeat byte."""
        output_log = handle.spec.output_log
        start = time.monotonic()
        deadline = start + timeout_s
        while time.monotonic() < deadline:
            try:
                if output_log.exists() and output_log.stat().st_size > 0:
                    return ReadyResult(True, "output_log_heartbeat", time.monotonic() - start)
            except OSError:  # pragma: no cover - transient stat race
                pass
            if not self.is_alive(handle):
                break
            time.sleep(0.05)
        return ReadyResult(False, "timeout", time.monotonic() - start)

    def stream_events(self, handle: AgentHandle) -> Iterator[AgentEvent]:
        """Yield AgentEvents parsed from the agent's events.jsonl (snapshot)."""
        events_path = handle.spec.runtime_dir / "agents" / handle.agent_id / "events.jsonl"
        if not events_path.exists():
            return
        for line in events_path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield AgentEvent(
                type=rec.get("type", "thinking"),
                timestamp=rec.get("timestamp", ""),
                payload=rec.get("payload", {}),
            )

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        engine = self._engines.get(handle.agent_id)
        if sig == AgentSignal.INTERRUPT:
            if engine is None:
                _logger.warning(
                    "INTERRUPT signal for un-hosted agent ignored",
                    extra={"agent_id": handle.agent_id},
                )
                return
            engine.send_interrupt()
        elif sig == AgentSignal.PROMPT_ADDITIONAL:
            # Nothing to do here — use deliver_prompt to add a prompt turn.
            return
        elif sig == AgentSignal.DONE_ACK:
            return

    def stop(self, handle: AgentHandle, *, reason: str) -> None:
        engine = self._engines.pop(handle.agent_id, None)
        thread = self._threads.pop(handle.agent_id, None)
        if engine is not None:
            engine.terminate()
        if thread is not None:
            thread.join(timeout=3.0)

    # -- helpers ----------------------------------------------------------

    def is_alive(self, handle: AgentHandle) -> bool:
        engine = self._engines.get(handle.agent_id)
        return bool(engine and engine.is_alive())

    def _default_command(self, spec: DispatchSpec) -> list[str]:
        """Build the launch argv from the launch-permission-policy on the spec.

        The policy is carried *entirely* by ``DispatchSpec.permission_mode`` +
        ``allowed_tools`` (OS-1a, #969) — there is no hardcoded permission flag.
        This mirrors the cmux-surface adapter
        (``coach.commands.spawn._claude_code_adapter``) exactly: a scoped
        ``--allowedTools`` allowlist is the leash, so any tool NOT listed fires
        a ``PermissionRequest`` and the decision surfaces. One policy, one
        source of truth — the cli-return path no longer suppresses decisions
        via the E014-forbidden ``--dangerously-skip-permissions`` flag.
        """
        cmd = ["claude", "--permission-mode", spec.permission_mode]
        if spec.allowed_tools:
            cmd += ["--allowedTools", " ".join(spec.allowed_tools)]
        assert_no_forbidden_launch_flags(cmd)
        return cmd


# --- TuiScrapeAgentController (deprecated legacy path) -------------------


class TuiScrapeAgentController:
    """DEPRECATED legacy screen-scrape control path (behind ``ATDD_USE_LEGACY_SPAWN=1``).

    Kept for one minor version as the §12.4 R-4 kill switch. Prompt delivery and
    interrupts are performed via an injected multiplexer-like backend (duck-typed,
    NOT imported — §3.3 forbids importing ``atdd.runtime.multiplexer`` here). The
    cli-return path (``ShimAgentController``) is the default and supported plane.
    """

    transport_name = "tui-scrape"

    def __init__(self, *, backend: object = None, surface_ref: object = None) -> None:
        import warnings

        warnings.warn(
            "TuiScrapeAgentController is the deprecated screen-scrape control "
            "path (ATDD_USE_LEGACY_SPAWN=1); cli-return (ShimAgentController) is "
            "the default. Removal target: 3.87.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._backend = backend
        self._surface_ref = surface_ref

    def spawn(self, spec: DispatchSpec) -> AgentHandle:
        return AgentHandle(
            agent_id=spec.agent_id, spec=spec, spawned_at=_now_iso(), transport="tui-scrape",
        )

    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:
        if self._backend is None:
            raise RuntimeError(
                "TuiScrapeAgentController.deliver_prompt requires an injected "
                "multiplexer backend (legacy paste path)"
            )
        # Inject AND submit via the legacy paste + Enter sequence.
        self._backend.paste_text(self._surface_ref, prompt)
        self._backend.send_key(self._surface_ref, "Enter")

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float) -> ReadyResult:
        return ReadyResult(True, "tui-scrape-assumed-ready", 0.0)

    def stream_events(self, handle: AgentHandle) -> Iterator[AgentEvent]:
        return iter(())

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        if sig == AgentSignal.INTERRUPT and self._backend is not None:
            self._backend.send_key(self._surface_ref, "C-c")

    def stop(self, handle: AgentHandle, *, reason: str) -> None:
        return None


# --- HeadlessPrintController (non-interactive) ---------------------------


class HeadlessPrintController:
    """``claude -p`` for CI / non-interactive runs (§4.8).

    Each prompt is a one-shot non-interactive invocation; stdout is appended to
    the agent's output.log.
    """

    transport_name = "headless-print"

    def __init__(self, *, base_command: Sequence[str] = ("claude", "-p")) -> None:
        self._base_command = list(base_command)
        self._procs: dict[str, object] = {}

    def spawn(self, spec: DispatchSpec) -> AgentHandle:
        spec.output_log.parent.mkdir(parents=True, exist_ok=True)
        return AgentHandle(
            agent_id=spec.agent_id, spec=spec, spawned_at=_now_iso(), transport="headless-print",
        )

    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:
        import subprocess

        spec = handle.spec
        spec.output_log.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, **dict(spec.env_overrides)}
        with spec.output_log.open("ab") as log_fh:
            proc = subprocess.Popen(
                [*self._base_command, prompt],
                cwd=str(spec.worktree_path),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
            )
        self._procs[handle.agent_id] = proc

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float) -> ReadyResult:
        return ReadyResult(True, "headless-print", 0.0)

    def stream_events(self, handle: AgentHandle) -> Iterator[AgentEvent]:
        return iter(())

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        proc = self._procs.get(handle.agent_id)
        if sig == AgentSignal.INTERRUPT and proc is not None:
            try:
                proc.terminate()  # type: ignore[attr-defined]
            except OSError as exc:  # pragma: no cover - race on exit
                _logger.debug("headless interrupt skipped", extra={"error": str(exc)})

    def stop(self, handle: AgentHandle, *, reason: str) -> None:
        proc = self._procs.pop(handle.agent_id, None)
        if proc is not None:
            try:
                proc.terminate()  # type: ignore[attr-defined]
            except OSError as exc:  # pragma: no cover - race on exit
                _logger.debug("headless stop skipped", extra={"error": str(exc)})


# --- CmuxAgentController (cmux-native launch, #978) -----------------------


def _default_cmux_runner(argv: Sequence[str]) -> str:
    """Run a cmux CLI command and return its stdout (default launch runner)."""
    import subprocess

    completed = subprocess.run(
        list(argv), capture_output=True, text=True, check=True,
    )
    return completed.stdout


class CmuxAgentController:
    """cmux-native launcher (#978): opens a cmux surface running the agent and
    seeds the first turn via the agent's **positional prompt** — no pty shim, no
    ``cli-return.jsonl`` inbox, no submit sentinel.

    Decision communication rides the cmux Feed (the wrapper's hooks fire because
    the surface sets ``CMUX_SURFACE_ID``); this controller never touches the Feed
    and never owns a pty. Liveness and signals go through the cmux CLI, not
    ``output.log``. The ``runner`` is injected so the launch shape is testable
    without a real cmux. ``ATDD_USE_LEGACY_SPAWN=1`` still selects the shim.
    """

    transport_name = "cmux-native"

    def __init__(
        self,
        *,
        agent_bin: str = "claude",
        cmux_bin: str = "cmux",
        runner: Optional[Callable[[Sequence[str]], str]] = None,
    ) -> None:
        self._agent_bin = agent_bin
        self._cmux_bin = cmux_bin
        self._runner = runner or _default_cmux_runner
        # agent_id -> launch stdout (carries the workspace/surface ref)
        self._launched: dict[str, str] = {}

    def _launch_argv(self, spec: DispatchSpec) -> list[str]:
        """Build (and guard) the cmux launch argv for ``spec`` — prompt-first seed."""
        from atdd.runtime.agent_control.cmux_launch import (
            build_agent_seed_argv,
            build_cmux_launch_argv,
        )

        agent_argv = build_agent_seed_argv(
            self._agent_bin,
            spec.prompt_text,
            permission_mode=spec.permission_mode,
            allowed_tools=tuple(spec.allowed_tools),
        )
        # Same E014 boundary guard every launch path runs (#969): no bypass flag
        # may reach a launch, or decisions would never surface to the Feed.
        assert_no_forbidden_launch_flags(agent_argv)
        return build_cmux_launch_argv(
            agent_argv,
            cwd=spec.worktree_path,
            name=_canonical_surface_name(spec.agent_id),
            cmux_bin=self._cmux_bin,
        )

    def spawn(self, spec: DispatchSpec) -> AgentHandle:
        result = self._runner(self._launch_argv(spec))
        self._launched[spec.agent_id] = result
        return AgentHandle(
            agent_id=spec.agent_id,
            spec=spec,
            spawned_at=_now_iso(),
            transport="cmux-native",
        )

    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:
        """Initial brief is seeded at launch (positional prompt). A mid-run
        correction is delivered to the surface via ``cmux send`` + ``send-key``
        (the agent's correct keyboard-protocol handling submits it)."""
        self._runner([self._cmux_bin, "send", prompt])
        self._runner([self._cmux_bin, "send-key", "Enter"])

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float) -> ReadyResult:
        # cmux owns process+pixels; a successful launch means the surface exists.
        # Liveness derives from cmux surface state, not an output.log heartbeat.
        return ReadyResult(True, "cmux-surface-launched", 0.0)

    def stream_events(self, handle: AgentHandle) -> Iterator[AgentEvent]:
        return iter(())

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        if sig == AgentSignal.INTERRUPT:
            self._runner([self._cmux_bin, "send-key", "C-c"])

    def stop(self, handle: AgentHandle, *, reason: str) -> None:
        self._launched.pop(handle.agent_id, None)


def _canonical_surface_name(agent_id: str) -> str:
    """Canonical cmux surface/workspace name for an agent id (coach.orchestration
    canonical-session-name shape, uppercased, no separators)."""
    return "ATDD" + "".join(ch for ch in agent_id if ch.isalnum()).upper()
