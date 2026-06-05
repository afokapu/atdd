"""``atdd.runtime.agent_control`` — the runtime agent-control layer (Child 6).

docs/coach-decomposition.md §4.8 / §13.6. Owns worker spawn, prompt delivery,
ready detection, agent done signals, and transport selection. **cmux-native is
the sole launch plane** (#978 / #979): cmux opens the surface running the agent
and the agent's positional prompt seeds AND auto-submits the first turn. The
legacy pty shim (cli-return / ``ShimAgentController``) and its
``ATDD_USE_LEGACY_SPAWN`` kill switch were decommissioned in #979 once the
cmux-native path soaked — that retired the cold-start heartbeat flake and the
#950 submit-sentinel bug from the launch path. ``HeadlessPrintController``
(``claude -p``) remains for CI / non-interactive runs.

Dependency rule (§3.3): this layer imports stdlib (+ subprocess) only. It MUST
NOT import ``atdd.coach.*``, ``atdd.train.*``, ``atdd.integrations.*``, or
``atdd.runtime.multiplexer``. Consequently ``DispatchSpec.persona`` is typed
``str`` (it carries an ``atdd.coach.core.types.Persona`` value, which is a
``StrEnum`` — importing the enum here would violate the import-discipline gate).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterator, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

__all__ = [
    "DispatchSpec",
    "ReadyResult",
    "AgentEvent",
    "AgentSignal",
    "AgentHandle",
    "AgentController",
    "HeadlessPrintController",
    "CmuxAgentController",
    "resolve_transport",
    "DEFAULT_TRANSPORT",
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
_DEFUNCT_SHIM_TRANSPORT = "cli-return"  # decommissioned launch transport (#979)
_LEGACY_OVERRIDE_ENV = "ATDD_CORRECTION_TRANSPORT"  # back-compat explicit override


def resolve_transport(env: Optional[Mapping[str, str]] = None) -> str:
    """Resolve the dispatch transport (§13.6, §12.4 R-4).

    ``cmux-native`` is the sole supported launch plane (#978 / #979): cmux opens
    the surface running the agent and the positional prompt seeds AND
    auto-submits the first turn (no pty shim, no cli-return inbox, no submit
    sentinel; decisions ride the cmux Feed hooks).

    An explicit ``ATDD_CORRECTION_TRANSPORT`` value is still honoured as a
    forward opt-in / test override — including the deprecated ``tui-scrape``
    direct-paste path. The one exception is the now-defunct ``cli-return``
    (the deleted shim): the deferred observer still uses that same env var to
    select its *mid-run correction* delivery, so a leftover ``cli-return``
    value falls through to ``cmux-native`` for *launch* rather than routing to a
    shim that no longer exists (#979).
    """
    env = os.environ if env is None else env
    override = str(env.get(_LEGACY_OVERRIDE_ENV, "")).strip().lower()
    if override and override != _DEFUNCT_SHIM_TRANSPORT:
        return override
    if override == _DEFUNCT_SHIM_TRANSPORT:
        _logger.info(
            "ignoring defunct cli-return launch transport; using cmux-native",
            extra={"override": override},
        )
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
