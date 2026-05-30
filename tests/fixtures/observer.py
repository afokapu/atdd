"""``FakeObserver`` — read-only event consumer double (Child 2).

The real ``atdd.observer`` (promoted to first-class in Child 10, §8) is a
strictly read-only consumer of ``events.jsonl`` / ``output.log``: it NEVER
writes orchestration state. This double models that contract — it can only
record what it observed; it exposes no method that mutates run state. The parity
runner hands it decision notifications so the harness can demonstrate a consumer
that watches the stream without writing to it.
"""
from __future__ import annotations


class FakeObserver:
    def __init__(self) -> None:
        self._observed: list[dict] = []

    def observe(self, event: dict) -> None:
        # Record-only; an observer never writes back to the event log.
        self._observed.append(dict(event))

    @property
    def observed(self) -> list[dict]:
        return list(self._observed)
