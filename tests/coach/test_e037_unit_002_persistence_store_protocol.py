# URN: test:govern-lifecycle:define-validator-report-and-persistence-materialization-contract:E037-UNIT-002-persistence-store-protocol
# Acceptance: acc:govern-lifecycle:E037-UNIT-002-persistence-store-protocol
"""Unit test for E037-UNIT-002 (docs/coach-decomposition.md §4.6, §4.7, §4.4).

``atdd.train.persistence`` exposes the §4.6 ``PersistenceStore`` Protocol (every
method), the §4.4 ``load_conventions`` signature, and ``IssueRecord``; the §4.7
run/event value types live in ``atdd.train.types``. Concrete bodies ship in
Child 7 — here the *contract surface* is asserted.
"""
from __future__ import annotations

import pathlib

import pytest

from atdd.train import types as train_types
from atdd.train.persistence import IssueRecord, PersistenceStore, load_conventions

pytestmark = pytest.mark.atdd_validator

# Every method from docs/coach-decomposition.md §4.6.
_REQUIRED_METHODS = {
    "create_run",
    "load_run",
    "list_runs",
    "append_event",
    "replay_events",
    "append_decision",
    "get_issue",
    "upsert_issue",
    "materialize_evidence",
}


def test_persistence_store_protocol_has_every_4_6_method():
    members = set(dir(PersistenceStore))
    missing = _REQUIRED_METHODS - members
    assert not missing, f"PersistenceStore missing §4.6 methods: {sorted(missing)}"


def test_load_conventions_is_signature_only():
    # Importable (acceptance) but unimplemented until Child 7 (§4.4).
    with pytest.raises(NotImplementedError):
        load_conventions(pathlib.Path("."))


def test_train_value_types_are_importable():
    for name in ("RunId", "RunStatus", "RunSummary", "RunState", "WaveResult", "TrainEvent"):
        assert hasattr(train_types, name), f"missing §4.7 type {name}"
    assert hasattr(IssueRecord, "__dataclass_fields__")
