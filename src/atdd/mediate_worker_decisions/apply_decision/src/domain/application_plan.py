"""Pure verdict -> WorkerInstruction planning (no I/O)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerInstruction:
    """What to deliver to the worker to apply a decision."""

    text: str


def plan_instruction(selected_option_id: str) -> WorkerInstruction:
    """The worker answers a prompt by receiving the selected option id + newline."""
    return WorkerInstruction(text=f"{selected_option_id}\n")
