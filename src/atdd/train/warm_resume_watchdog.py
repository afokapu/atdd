"""Warm-resume hang/timeout watchdog (#1079, WMBT M003).

The coach hung at a PLANNED->RED warm-resume (drive_single_issue → is_warm_resume
branch in issue_runner.py) — the spawn/advance blocked with no upper time bound
and no record, so the #1082 orchestrator loop would stall forever. This watchdog
wraps the warm-resume action in a bounded budget: on overrun it aborts, records a
structured escalation keyed to issue + transition + elapsed, and returns a
timed-out result instead of blocking unbounded. A within-budget action completes
normally with no timeout fired.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

# Sane positive default budget (seconds). Never disabled by an unset config.
DEFAULT_WARM_RESUME_BUDGET_S = 300.0


@dataclass(frozen=True)
class WarmResumeOutcome:
    """Outcome of a bounded warm-resume the orchestrator can act on."""

    status: str  # "completed" | "timed_out"
    elapsed_s: float
    result: Any


def resolve_warm_resume_budget(value: Optional[float]) -> float:
    """Resolve the warm-resume timeout budget.

    Honors a custom ``value``, defaults to a sane positive value when unset, and
    rejects non-positive values rather than silently disabling the watchdog.
    """
    if value is None:
        return DEFAULT_WARM_RESUME_BUDGET_S
    budget = float(value)
    if budget <= 0:
        raise ValueError(f"warm-resume timeout budget must be positive, got {value!r}")
    return budget


def run_warm_resume_with_timeout(
    action: Callable[[], Any],
    *,
    issue_number: int,
    transition: str,
    budget_s: float,
    on_timeout: Callable[[dict], None],
) -> WarmResumeOutcome:
    """Run ``action`` under a ``budget_s`` watchdog.

    On overrun, ``on_timeout`` is called with a structured record (issue,
    transition, elapsed) and a ``timed_out`` outcome is returned — the call
    never blocks past the budget. Otherwise the action's result is returned.
    """
    box: dict = {}

    def _runner() -> None:
        box["result"] = action()

    worker = threading.Thread(target=_runner, daemon=True)
    start = time.monotonic()
    worker.start()
    worker.join(budget_s)
    elapsed = time.monotonic() - start

    if worker.is_alive():
        on_timeout(
            {
                "issue_number": issue_number,
                "transition": transition,
                "elapsed_s": elapsed,
            }
        )
        return WarmResumeOutcome(status="timed_out", elapsed_s=elapsed, result=None)

    return WarmResumeOutcome(
        status="completed", elapsed_s=elapsed, result=box.get("result")
    )
