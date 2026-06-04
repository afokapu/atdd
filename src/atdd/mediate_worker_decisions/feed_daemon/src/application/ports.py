"""Ports for the feed daemon (application boundary).

The daemon reuses bridge-cmux-feed's ``FeedSource`` (poll) and the production
``FeedRunnerUseCase`` (decide/escalate) wholesale; these ports cover only what
the daemon adds: durable ledgers, a pacing sleeper, a single-instance lock, and
a termination stop-signal.
"""
from __future__ import annotations

from typing import Protocol

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    Escalation,
    Verdict,
)


class EscalationSink(Protocol):
    """Durably records a human escalation (and loudly surfaces it)."""

    def record(self, escalation: Escalation) -> None: ...


class VerdictLedger(Protocol):
    """Durably records an auto-applied verdict (audit + restart re-hydration)."""

    def record(self, verdict: Verdict) -> None: ...


class Sleeper(Protocol):
    """Paces the poll loop; injected so tests stay instant."""

    def sleep(self, seconds: float) -> None: ...


class Lock(Protocol):
    """Single-instance guard: acquire() is False when another holder is alive."""

    def acquire(self) -> bool: ...

    def release(self) -> None: ...


class StopSignal(Protocol):
    """True once a SIGINT/SIGTERM (or test) has requested shutdown."""

    def is_set(self) -> bool: ...
