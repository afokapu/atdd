"""Domain value objects for a sensed worker decision (pure, no I/O).

These mirror the ``commons:decision:request`` contract
(``contracts/commons/decision/request.schema.json``). They are frozen and
constructed only from plain data, so the parser and use case stay unit-testable
without any cmux/runtime dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class Option:
    """One selectable answer in a decision prompt."""

    id: str
    label: str


@dataclass(frozen=True)
class WorkerRef:
    """The worker agent a decision was sensed from."""

    surface_id: str
    run_id: Optional[str] = None
    agent_handle_ref: Optional[str] = None


@dataclass(frozen=True)
class DecisionPrompt:
    """The structured decision extracted from worker surface text."""

    raw_text: str
    question: str
    options: Tuple[Option, ...]


@dataclass(frozen=True)
class DecisionRequest:
    """A normalized, contract-shaped worker decision request."""

    request_id: str
    worker: WorkerRef
    prompt: DecisionPrompt
    source: str  # "cmux_notification" | "emit_cli"
    created_at: str
    notification_hash: Optional[str] = None

    def to_contract(self) -> dict:
        """Serialize to the ``commons:decision:request`` JSON shape.

        notify-hook and emit-CLI both serialize through this single method, so
        the two entry paths cannot diverge (WMBT D001).
        """
        provenance: dict = {"source": self.source}
        if self.notification_hash is not None:
            provenance["notification_hash"] = self.notification_hash
        return {
            "request_id": self.request_id,
            "created_at": self.created_at,
            "worker": _compact(
                {
                    "surface_id": self.worker.surface_id,
                    "run_id": self.worker.run_id,
                    "agent_handle_ref": self.worker.agent_handle_ref,
                }
            ),
            "prompt": {
                "raw_text": self.prompt.raw_text,
                "question": self.prompt.question,
                "options": [{"id": o.id, "label": o.label} for o in self.prompt.options],
            },
            "provenance": provenance,
        }


def _compact(d: dict) -> dict:
    """Drop keys whose value is None (contract uses additionalProperties: false)."""
    return {k: v for k, v in d.items() if v is not None}
