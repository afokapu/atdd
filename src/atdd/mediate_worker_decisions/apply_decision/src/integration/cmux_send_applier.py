"""WorkerApplier adapter that delivers the answer to a worker via the cmux CLI.

For workers that are plain processes (a shell prompt, a non-agent tool) rather
than shim-wrapped agents, the answer is delivered by typing the selected option
onto the worker surface and pressing Enter. (Agent workers use
``AgentControlApplier`` over runtime.agent_control instead.) cmux surface refs
are workspace-scoped, so ``send``/``send-key`` take ``--workspace``.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.src.domain.application_plan import (
    WorkerInstruction,
)
from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux


class CmuxSendApplier:
    def __init__(self, workspace_id: str) -> None:
        self._workspace = workspace_id

    def apply(self, handle_ref: str, instruction: WorkerInstruction) -> None:
        # handle_ref is the worker's cmux surface id.
        run_cmux("send", "--workspace", self._workspace,
                 "--surface", handle_ref, instruction.text.rstrip("\n"))
        run_cmux("send-key", "--workspace", self._workspace,
                 "--surface", handle_ref, "Enter")
