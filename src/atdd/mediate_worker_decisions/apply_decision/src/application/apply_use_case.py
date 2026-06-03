"""Apply use case: deliver an auto_apply verdict once; record every outcome.

- human_required verdicts are NEVER delivered (WMBT R001).
- the same verdict is delivered at most once (WMBT E002).
- every outcome — applied, escalated, or failed — is recorded (WMBT K001).
- a delivery failure is recorded with its error and logged, never swallowed
  (WMBT M002; coder.logging: log-or-raise, structured extra).
"""
from __future__ import annotations

import logging
from typing import Callable

from atdd.mediate_worker_decisions.apply_decision.src.application.ports import (
    AppliedGuard,
    DecisionLedger,
    WorkerApplier,
)
from atdd.mediate_worker_decisions.apply_decision.src.domain.application_plan import (
    plan_instruction,
)
from atdd.mediate_worker_decisions.apply_decision.src.domain.idempotency_key import (
    idempotency_key,
)
from atdd.mediate_worker_decisions.apply_decision.src.domain.record import (
    APPLICATION_FAILED,
    APPLIED,
    ESCALATED,
    DecisionRecord,
)

_log = logging.getLogger(__name__)

_HUMAN_REQUIRED = "human_required"


class ApplyDecisionUseCase:
    def __init__(
        self,
        applier: WorkerApplier,
        ledger: DecisionLedger,
        guard: AppliedGuard,
        id_factory: Callable[[], str],
        ts_factory: Callable[[], str],
    ) -> None:
        self._applier = applier
        self._ledger = ledger
        self._guard = guard
        self._id = id_factory
        self._now = ts_factory

    def apply(self, request: object, verdict: object) -> DecisionRecord:
        key = idempotency_key(request.request_id, verdict.verdict_id)  # type: ignore[attr-defined]

        # R001: an escalated / human_required verdict is never delivered.
        if verdict.disposition == _HUMAN_REQUIRED:  # type: ignore[attr-defined]
            return self._record(request, verdict, ESCALATED, key)

        # E002: deliver at most once.
        if self._guard.seen(key):
            _log.info(
                "verdict already applied; recording deduped no-op",
                extra={"idempotency_key": key, "request_id": request.request_id},  # type: ignore[attr-defined]
            )
            return self._record(request, verdict, APPLIED, key)

        self._guard.mark(key)
        instruction = plan_instruction(verdict.selected_option_id)  # type: ignore[attr-defined]
        handle = (
            getattr(request.worker, "agent_handle_ref", None)  # type: ignore[attr-defined]
            or request.worker.surface_id  # type: ignore[attr-defined]
        )
        try:
            self._applier.apply(handle, instruction)
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            _log.error(
                "worker application failed",
                extra={"request_id": request.request_id, "error": str(exc)},  # type: ignore[attr-defined]
            )
            return self._record(request, verdict, APPLICATION_FAILED, key, error=str(exc))

        return self._record(request, verdict, APPLIED, key)

    def _record(self, request, verdict, disposition, key, error=None) -> DecisionRecord:
        record = DecisionRecord(
            record_id=self._id(),
            request_id=request.request_id,
            recorded_at=self._now(),
            disposition=disposition,
            idempotency_key=key,
            verdict_id=getattr(verdict, "verdict_id", None),
            request=request.to_contract(),
            verdict=verdict.to_contract(),
            error=error,
        )
        self._ledger.record(record)
        return record
