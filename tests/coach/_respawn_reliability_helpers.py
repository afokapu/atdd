"""Shared fakes for the #1079 spawn/respawn reliability primitive RED tests.

These recorders model the collaborators the four primitives drive — an
``AgentController`` (E031), a GitHub label store (E032), and a surface
registry (C002) — without spawning real processes, surfaces, or `gh` calls.
They are deliberately minimal: each records the calls a test asserts on.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from atdd.runtime.agent_control import AgentHandle, AgentSignal, DispatchSpec


def make_spec(agent_id: str, *, persona: str = "coder") -> DispatchSpec:
    """Build a throwaway ``DispatchSpec`` for the next-phase relaunch."""
    return DispatchSpec(
        agent_id=agent_id,
        persona=persona,
        worktree_path=Path("/tmp") / agent_id,
        prompt_text="",
        correction_inbox=Path("/tmp") / agent_id / "cli-return.jsonl",
        output_log=Path("/tmp") / agent_id / "output.log",
        runtime_dir=Path("/tmp") / agent_id / "runtime",
        env_overrides={},
        transport="cli-return",
        permission_mode="acceptEdits",
        allowed_tools=("Read",),
    )


def make_handle(agent_id: str, *, persona: str = "coder") -> AgentHandle:
    """Build an ``AgentHandle`` with a throwaway spec for ordering/scope tests."""
    spec = make_spec(agent_id, persona=persona)
    return AgentHandle(
        agent_id=agent_id, spec=spec, spawned_at="2026-06-12T00:00:00Z",
        transport="cli-return",
    )


class FakeAgentController:
    """Records signal/stop/spawn order and exposes a controllable liveness probe.

    ``die_on_stop`` models a successful reap (the process dies when ``stop`` is
    called). Set it False to model a kill that cannot be confirmed — the worker
    stays alive after ``stop`` so the respawn guard must refuse.
    """

    def __init__(self, *, die_on_stop: bool = True) -> None:
        self.calls: list[tuple] = []
        self._alive: dict[str, bool] = {}
        self._die_on_stop = die_on_stop
        self.spawned: list[AgentHandle] = []

    # --- liveness probe the kill-and-confirm guard relies on (E031) ---
    def is_alive(self, handle: AgentHandle) -> bool:
        return self._alive.get(handle.agent_id, False)

    def mark_alive(self, agent_id: str) -> None:
        self._alive[agent_id] = True

    # --- AgentController surface used by the respawn path ---
    def spawn(self, spec: DispatchSpec) -> AgentHandle:
        self.calls.append(("spawn", spec.agent_id))
        self._alive[spec.agent_id] = True
        handle = make_handle(spec.agent_id, persona=spec.persona)
        self.spawned.append(handle)
        return handle

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None:
        self.calls.append(("signal", handle.agent_id, str(sig)))

    def stop(self, handle: AgentHandle, *, reason: str) -> None:
        self.calls.append(("stop", handle.agent_id))
        if self._die_on_stop:
            self._alive[handle.agent_id] = False

    # --- no-op protocol members (unused by the respawn path under test) ---
    def deliver_prompt(self, handle: AgentHandle, prompt: str) -> None:  # pragma: no cover
        self.calls.append(("deliver_prompt", handle.agent_id))

    def wait_ready(self, handle: AgentHandle, *, timeout_s: float):  # pragma: no cover
        return None

    def stream_events(self, handle: AgentHandle):  # pragma: no cover
        return iter(())

    def op_names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def targets_of(self, op: str) -> list[str]:
        return [c[1] for c in self.calls if c[0] == op]


class FakeLabelStore:
    """In-memory GitHub phase-label store for the idempotent advance (E032).

    ``current`` is the issue's live ``atdd:<phase>`` value. ``swaps`` records
    every label mutation so a test can assert exactly-one / no-op / refused.
    """

    def __init__(self, current: str) -> None:
        self.current = current
        self.swaps: list[str] = []

    def read_phase(self, issue_number: int) -> str:
        return self.current

    def swap_label(self, issue_number: int, target: str) -> None:
        self.swaps.append(target)
        self.current = target


class FakeSurfaceRegistry:
    """Models the issue->surface binding + liveness + paste sink (C002).

    ``live`` is the set of surface refs the registry currently reports live for
    the issue. ``pastes`` records (ref, prompt); ``reaped`` records refs closed.
    """

    def __init__(self, live: Optional[list[str]] = None) -> None:
        self._live: list[str] = list(live or [])
        self.pastes: list[tuple[str, str]] = []
        self.reaped: list[str] = []
        self.created: list[str] = []
        self._seq = 0

    def live_surfaces_for(self, issue_number: int) -> list[str]:
        return list(self._live)

    def is_live(self, ref: str) -> bool:
        return ref in self._live

    def create_surface(self, issue_number: int) -> str:
        self._seq += 1
        ref = f"surface-new-{issue_number}-{self._seq}"
        self._live.append(ref)
        self.created.append(ref)
        return ref

    def reap_surface(self, ref: str) -> None:
        self.reaped.append(ref)
        if ref in self._live:
            self._live.remove(ref)

    def paste(self, ref: str, prompt: str) -> None:
        self.pastes.append((ref, prompt))
