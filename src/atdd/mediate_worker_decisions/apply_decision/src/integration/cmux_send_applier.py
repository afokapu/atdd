"""WorkerApplier adapter that delivers the answer to a worker via the cmux CLI.

For workers that are plain processes (a shell prompt, a non-agent tool) rather
than shim-wrapped agents, the answer is delivered by typing the selected option
onto the worker surface and pressing Enter. (Agent workers use
``AgentControlApplier`` over runtime.agent_control instead.) cmux surface refs
are workspace-scoped, so ``send``/``send-key`` take ``--workspace``.

.. deprecated:: 3.88.0
   Part of the screen-scrape path (keystroke delivery), superseded by the
   bridge-cmux-feed Feed integration
   (``atdd.mediate_worker_decisions.bridge_cmux_feed``). Removal: 3.90.0.
   (``AgentControlApplier`` — agent_control delivery — is NOT deprecated.)
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.apply_decision.src.domain.application_plan import (
    WorkerInstruction,
)
from atdd.mediate_worker_decisions.commons.cmux_cli import run_cmux


class CmuxSendApplier:
    def __init__(self, workspace_id: str) -> None:
        import warnings

        warnings.warn(
            "CmuxSendApplier is deprecated since 3.88.0; the cmux Feed is the "
            "channel now — use atdd.mediate_worker_decisions.bridge_cmux_feed."
            "composition.build_feed_runner. Removal: 3.90.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._workspace = workspace_id

    def apply(self, handle_ref: str, instruction: WorkerInstruction) -> None:
        # handle_ref is the worker's cmux surface id.
        run_cmux("send", "--workspace", self._workspace,
                 "--surface", handle_ref, instruction.text.rstrip("\n"))
        run_cmux("send-key", "--workspace", self._workspace,
                 "--surface", handle_ref, "Enter")
