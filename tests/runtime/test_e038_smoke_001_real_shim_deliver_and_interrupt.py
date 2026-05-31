# URN: test:govern-lifecycle:extract-runtime-agent-control-and-close-spawn-cluster:E038-SMOKE-001-real-shim-deliver-and-interrupt
# Acceptance: acc:govern-lifecycle:E038-SMOKE-001-real-shim-deliver-and-interrupt
# WMBT: wmbt:govern-lifecycle:E038
# Phase: SMOKE
# Assertion: behavioral
# Layer: runtime
"""E038-SMOKE-001 — real ShimAgentController over a real pty (closes #871/#872).

docs/coach-decomposition.md §13.6 acceptance:
  * "A test asserts the prompt primed via cli-return.jsonl is observable in the
     agent's TUI within 5s of spawn (closes #872)."
  * "A test asserts a stdin INTERRUPT signal terminates the wrapped agent
     (closes #871)."

This drives the ACTUAL pty + cli-return.jsonl + output.log path against a real
child process (no in-memory stub, no cmux paste) — the proper integration check.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

# A real child agent: echo each submitted line back, prefixed, so a completed
# (i.e. submitted) line is observable in output.log. An un-submitted prompt
# (no trailing newline) would never complete readline → never echo → the #872
# regression would fail this test.
_FAKE_AGENT = (
    "import sys\n"
    "for line in sys.stdin:\n"
    "    sys.stdout.write('GOT:' + line)\n"
    "    sys.stdout.flush()\n"
)


def _spec(runtime_dir: Path, agent_id: str):
    from atdd.runtime.agent_control import DispatchSpec

    agent_dir = runtime_dir / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return DispatchSpec(
        agent_id=agent_id,
        persona="coder",
        worktree_path=runtime_dir,
        prompt_text="launch",
        correction_inbox=agent_dir / "cli-return.jsonl",
        output_log=agent_dir / "output.log",
        runtime_dir=runtime_dir,
        env_overrides={},
        transport="cli-return",
        permission_mode="acceptEdits",
        allowed_tools=(),
    )


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def test_real_shim_delivers_submitted_prompt_and_interrupts(tmp_path):
    from atdd.runtime.agent_control import AgentSignal, ShimAgentController

    # Open the ready gate immediately so the delivery is not held behind the
    # bootstrap delay during the test.
    import os

    monkey = {
        "ATDD_SHIM_BOOTSTRAP_DELAY_S": "0",
    }
    saved = {k: os.environ.get(k) for k in monkey}
    os.environ.update(monkey)
    try:
        controller = ShimAgentController()
        spec = _spec(tmp_path, "coder-smoke-a")
        handle = controller.spawn(
            spec, agent_command=[sys.executable, "-u", "-c", _FAKE_AGENT]
        )
        try:
            ready = controller.wait_ready(handle, timeout_s=5.0)
            assert ready.is_ready

            controller.deliver_prompt(handle, "PING-7e3f")

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if "GOT:PING-7e3f" in _read(spec.output_log):
                    break
                time.sleep(0.1)
            assert "GOT:PING-7e3f" in _read(spec.output_log), (
                "delivered prompt was not injected-and-submitted into the real "
                f"agent within 5s; output.log={_read(spec.output_log)!r}"
            )

            controller.signal(handle, AgentSignal.INTERRUPT)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if not controller.is_alive(handle):
                    break
                time.sleep(0.1)
            assert not controller.is_alive(handle), "agent survived INTERRUPT"
        finally:
            controller.stop(handle, reason="test-teardown")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
