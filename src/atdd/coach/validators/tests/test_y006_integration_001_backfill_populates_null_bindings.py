# URN: test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-001-backfill-populates-null-bindings
# Acceptance: acc:govern-lifecycle:Y006-INTEGRATION-001-backfill-populates-null-bindings
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: A backfill resolves each null-feature work item to a feature in plan/ and writes it, reporting rather than guessing where it cannot resolve.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:Y006-INTEGRATION-001-backfill-populates-null-bindings
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:Y006

Purpose: the issues minted before the binding existed must get one.

Derive-or-require at mint only covers issues minted AFTER the fix. Measured
2026-07-28: 638 of 808 stored work items carry no feature, and #1626, #1627,
#1630 and #1631 all read ``feature: None``.

The backfill entry point does not exist yet. It is resolved dynamically through
``optional_attr`` so its absence is a behavioural assertion naming the missing
surface, not an ImportError at collection time.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    TRAIN_URN_IN_FEATURE_SLOT,
    control_root,
    open_store,
    optional_attr,
    read_issue_data,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_BACKFILL_MODULE = "atdd.coach.commands.issue_feature_binding"
_BACKFILL_ATTR = "backfill_feature_bindings"

# One issue per resolution shape.
RESOLVABLE = 92001   # body declares a feature that resolves in plan/
TRAIN_DRIFT = 92002  # body declares a train URN in the Feature row (#1626 shape)
SILENT = 92003       # declares nothing
ALREADY_BOUND = 92004


def _backfill():
    fn = optional_attr(_BACKFILL_MODULE, _BACKFILL_ATTR)
    assert fn is not None, (
        f"no backfill entry point: expected {_BACKFILL_MODULE}.{_BACKFILL_ATTR}. "
        "638 of 808 work items carry no feature and nothing can populate them."
    )
    return fn


@pytest.fixture()
def seeded(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug="resolvable", issue_number=RESOLVABLE, feature=None,
               body=f"| Feature | `{FEATURE_URN}` |")
    seed_issue(store, slug="train-drift", issue_number=TRAIN_DRIFT, feature=None,
               body=f"| Feature | `{TRAIN_URN_IN_FEATURE_SLOT}` |")
    seed_issue(store, slug="silent", issue_number=SILENT, feature=None, body="no metadata table")
    seed_issue(store, slug="already-bound", issue_number=ALREADY_BOUND, feature=FEATURE_URN,
               body=f"| Feature | `{FEATURE_URN}` |")
    return root, store


def test_backfill_writes_a_resolvable_declaration(seeded) -> None:
    """A body-declared feature that resolves in plan/ is written to the store."""
    root, store = seeded
    _backfill()(control_root=root)

    assert read_issue_data(store, RESOLVABLE)["feature"] == FEATURE_URN


def test_backfill_refuses_to_manufacture_a_binding_from_a_train_urn(seeded) -> None:
    """The drift it was built to find must not become the binding it writes."""
    root, store = seeded
    report = _backfill()(control_root=root)

    assert read_issue_data(store, TRAIN_DRIFT)["feature"] is None, (
        "a train identity was written into the feature field — the backfill "
        "manufactured a binding out of the #1626 drift"
    )
    assert TRAIN_DRIFT in getattr(report, "unresolved", ()), (
        "the train-URN issue was neither bound nor reported as unresolved"
    )


def test_backfill_reports_rather_than_guesses_when_nothing_is_declared(seeded) -> None:
    """An issue declaring nothing is left null and named in the report."""
    root, store = seeded
    report = _backfill()(control_root=root)

    assert read_issue_data(store, SILENT)["feature"] is None
    assert SILENT in getattr(report, "unresolved", ()), (
        "an unbindable issue was silently skipped instead of reported"
    )


def test_backfill_is_idempotent_and_never_overwrites(seeded) -> None:
    """A second run writes nothing further and preserves existing bindings."""
    root, store = seeded
    fn = _backfill()

    first = fn(control_root=root)
    second = fn(control_root=root)

    assert getattr(second, "written", None) == (), (
        "the second backfill run wrote again — it is not idempotent"
    )
    assert set(getattr(first, "unresolved", ())) == set(getattr(second, "unresolved", ())), (
        "the unresolved set changed between two identical runs"
    )
    assert read_issue_data(store, ALREADY_BOUND)["feature"] == FEATURE_URN, (
        "an already-populated binding was overwritten"
    )
