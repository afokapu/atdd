"""WorkerApplier adapter that delivers the answer to a worker via the cmux CLI.

For workers that are plain processes (a shell prompt, a non-agent tool) rather
than shim-wrapped agents, the answer is delivered by typing the selected option
onto the worker surface and pressing Enter. (Agent workers use
``AgentControlApplier`` over runtime.agent_control instead.) cmux surface refs
are workspace-scoped, so ``send``/``send-key`` take ``--workspace``.
"""
from __future__ import annotations

import subprocess

from atdd.mediate_worker_decisions.apply_decision.src.domain.application_plan import (
    WorkerInstruction,
)


class CmuxSendApplier:
    def __init__(self, workspace_id: str, cmux_bin: str = "cmux") -> None:
        self._workspace = workspace_id
        self._cmux = cmux_bin

    def apply(self, handle_ref: str, instruction: WorkerInstruction) -> None:
        # handle_ref is the worker's cmux surface id.
        subprocess.run(
            [self._cmux, "send", "--workspace", self._workspace,
             "--surface", handle_ref, instruction.text.rstrip("\n")],
            capture_output=True, text=True, timeout=15, check=True,
        )
        subprocess.run(
            [self._cmux, "send-key", "--workspace", self._workspace,
             "--surface", handle_ref, "Enter"],
            capture_output=True, text=True, timeout=15, check=True,
        )
