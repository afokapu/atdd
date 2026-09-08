# URN: test:govern-lifecycle:bind-issue-feature:Y006-UNIT-001-revise-writes-the-feature-to-the-store
# Acceptance: acc:govern-lifecycle:Y006-UNIT-001-revise-writes-the-feature-to-the-store
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: `atdd author issue --revise <N> --feature <urn>` writes the feature onto the authoritative work item instead of accepting the flag and discarding it.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:Y006-UNIT-001-revise-writes-the-feature-to-the-store
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:Y006

Purpose: the revise path must carry `--feature` all the way into the store.

Measured 2026-07-28 across eight issues: the body metadata table updated on all
eight and `work_item.data.feature` stayed NULL on all eight, because
`_run_issue_revise` -> `_publish_revision` -> `revise_issue` ->
`revise_work_item_issue` thread only `body` and `issue_type`. `args.feature`
appears nowhere on the revise path.

Fails today because `revise_work_item_issue` has no `feature` parameter — a
behavioural assertion on stored state, not an import error.
"""
from __future__ import annotations

import inspect

import pytest

from atdd.state.work_item_writer import revise_work_item_issue

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 91635


def _seeded(tmp_path):
    root = control_root(tmp_path)
    store = open_store(root)
    seed_issue(store, slug="bind-issue-feature-probe", issue_number=_ISSUE,
               feature=None, body="| Feature | `none` |")
    return root, store


def _revise(store, issue_number, **kwargs):
    """Call the store writer, asserting first that it can receive the fields.

    Calling with an unsupported keyword would raise ``TypeError`` — a crash,
    not a behavioural report. The precondition is asserted so the RED failure
    names the missing parameter instead of surfacing an interpreter error.
    """
    accepted = set(inspect.signature(revise_work_item_issue).parameters)
    missing = sorted(k for k in kwargs if k not in accepted)
    assert not missing, (
        f"revise_work_item_issue cannot receive {missing} — `atdd author issue "
        f"--revise` accepts those flags and the store writer has no parameter "
        f"for them, so the values are discarded (#1635 Break 4)"
    )
    return revise_work_item_issue(store.conn, issue_number, **kwargs)


def test_revise_with_feature_alone_writes_it_to_the_store(tmp_path) -> None:
    """`--feature` on its own reaches the authoritative store write."""
    _root, store = _seeded(tmp_path)

    _revise(store, _ISSUE, feature=FEATURE_URN)

    assert read_issue_data(store, _ISSUE)["feature"] == FEATURE_URN, (
        "revise accepted a feature URN and did not persist it — this is the "
        "measured silent drop (#1635 Break 4)"
    )


def test_revise_with_feature_and_body_writes_both(tmp_path) -> None:
    """Neither field overwrites the other when both are supplied."""
    _root, store = _seeded(tmp_path)
    new_body = "| Feature | `%s` |" % FEATURE_URN

    _revise(store, _ISSUE, body=new_body, feature=FEATURE_URN)

    data = read_issue_data(store, _ISSUE)
    assert data["feature"] == FEATURE_URN, "the feature was dropped when a body accompanied it"
    assert data["body"] == new_body, "the body was dropped when a feature accompanied it"


def test_revise_without_feature_never_clears_an_existing_binding(tmp_path) -> None:
    """A body-only revision must leave an existing binding untouched."""
    root = control_root(tmp_path)
    store = open_store(root)
    seed_issue(store, slug="already-bound", issue_number=_ISSUE + 1,
               feature=FEATURE_URN)

    _revise(store, _ISSUE + 1, body="unrelated body edit")

    assert read_issue_data(store, _ISSUE + 1)["feature"] == FEATURE_URN, (
        "a revision naming no feature cleared the existing binding"
    )


def test_no_accepted_revise_flag_is_dropped() -> None:
    """Every flag the revise parser declares must reach the store writer.

    Asserted against the parser's own declared arguments rather than a
    hand-maintained list, so a future flag added to the CLI and forgotten in
    the call chain is caught by the same guard that catches `--feature` today.
    """
    accepted = set(inspect.signature(revise_work_item_issue).parameters)
    for flag in ("body", "issue_type", "feature"):
        assert flag in accepted, (
            f"`--{flag.replace('_', '-')}` is accepted by `atdd author issue "
            f"--revise` but revise_work_item_issue cannot receive it, so the "
            f"value is discarded between the CLI and the store"
        )
