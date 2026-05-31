"""Shared test doubles + dry-run harness for the lifecycle parity gate (Child 2).

Everything the parity test (``tests/lifecycle/test_full_issue_parity.py``) and
its conftest import lives here. These are test-only fakes that stand in for
layers shipped by later children:

| Export                    | Stands in for                         | Real impl ships in |
|---------------------------|---------------------------------------|--------------------|
| ``FakeGitHub``            | ``atdd.integrations.github``          | Child 4            |
| ``FakeAgent``             | ``atdd.runtime.agent_control``        | Child 6            |
| ``FakeObserver``          | ``atdd.observer``                     | Child 10           |
| ``InMemoryPersistenceStore`` | ``atdd.train.persistence`` store   | Child 7            |
| ``LocalDryRunRunner``     | ``atdd.train.runners.jsonl``          | Child 8            |
| ``PolicyHandle``          | ``atdd.train.runner_iface``           | Child 8            |
| ``load_conventions``      | ``atdd.train.persistence``            | Child 7            |

The policy authority under test is the **real** Child-1 ``atdd.coach.core``.
"""
from __future__ import annotations

from .agent import FakeAgent
from .conventions import load_conventions
from .github import FakeGitHub, FakeIssue, FakePr
from .observer import FakeObserver
from .persistence import InMemoryPersistenceStore, StoredEvent
from .policy import PolicyHandle
from .runner import LocalDryRunRunner, MergeBlocked, RunStatus

__all__ = [
    "FakeAgent",
    "FakeGitHub",
    "FakeIssue",
    "FakePr",
    "FakeObserver",
    "InMemoryPersistenceStore",
    "StoredEvent",
    "LocalDryRunRunner",
    "MergeBlocked",
    "RunStatus",
    "PolicyHandle",
    "load_conventions",
]
