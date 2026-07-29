# URN: test:govern-lifecycle:bind-issue-feature:L003-UNIT-001-resolver-reads-the-feature-wmbts
# Acceptance: acc:govern-lifecycle:L003-UNIT-001-resolver-reads-the-feature-wmbts
# WMBT: wmbt:govern-lifecycle:L003
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The resolver walks issue -> stored feature URN -> feature YAML -> its wmbts: list, reading plan/ off disk with no provider call.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:L003-UNIT-001-resolver-reads-the-feature-wmbts
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:L003

Purpose: the WMBTs a coach surface shows must be the ones the planner authored.

`issue_lifecycle.py::_fetch_sub_issues` shells out to
`gh issue list --label atdd-wmbt --search "wmbt:<slug> in:title"` and never
touches plan/. #1477 removed the command that minted those labels with no
replacement; the 56 that exist are all pre-#1477 leftovers, newest #1059.

Observed three times during this issue's own lifecycle: `atdd coach enter 1635`
printed "WMBTs: none found" at INIT, at PLANNED and at RED, while the issue
carried Y006, C011 and L003 on the plan graph.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    FEATURE_WMBT,
    control_root,
    open_store,
    optional_attr,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_RESOLVER_MODULE = "atdd.coach.commands.issue_feature_binding"
_RESOLVER_ATTR = "resolve_wmbts_for_issue"

_ISSUE = 96001
_EMPTY_ISSUE = 96002
_SECOND_WMBT = "wmbt:govern-lifecycle:C011"


def _resolver():
    fn = optional_attr(_RESOLVER_MODULE, _RESOLVER_ATTR)
    assert fn is not None, (
        f"no plan-backed WMBT resolver: expected {_RESOLVER_MODULE}.{_RESOLVER_ATTR}. "
        "The only lookup today is the decommissioned atdd-wmbt label search."
    )
    return fn


@pytest.fixture()
def bound(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root, wmbts=(FEATURE_WMBT, _SECOND_WMBT))
    store = open_store(root)
    seed_issue(store, slug="plan-backed-probe", issue_number=_ISSUE, feature=FEATURE_URN)
    return root, store


@pytest.fixture()
def no_gh(monkeypatch):
    """Any subprocess call fails loudly — resolution must not shell out."""
    import subprocess

    def _forbidden(*args, **kwargs):  # pragma: no cover - the point is not to run
        raise AssertionError(
            f"the resolver shelled out to a subprocess: {args!r}. Resolution must "
            "read plan/ off disk, not query a provider."
        )

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "check_output", _forbidden)
    return _forbidden


def test_resolver_returns_the_declared_wmbts_in_order(bound, no_gh) -> None:
    root, _store = bound

    result = _resolver()(_ISSUE, control_root=root)

    assert list(getattr(result, "wmbts", result)) == [FEATURE_WMBT, _SECOND_WMBT], (
        "the resolver did not return the feature YAML's wmbts: list verbatim"
    )


def test_resolution_makes_no_subprocess_or_network_call(bound, no_gh) -> None:
    """The stubbed subprocess entry points must never be invoked."""
    root, _store = bound

    _resolver()(_ISSUE, control_root=root)  # `no_gh` raises if a subprocess is used


def test_an_empty_wmbts_list_is_distinguishable_from_a_failure(bound, no_gh) -> None:
    """A feature declaring no WMBTs is a genuine empty answer, not an error."""
    root, store = bound
    write_plan_tree(root, wmbts=())
    seed_issue(store, slug="empty-feature-probe", issue_number=_EMPTY_ISSUE,
               feature=FEATURE_URN)

    result = _resolver()(_EMPTY_ISSUE, control_root=root)

    assert list(getattr(result, "wmbts", result)) == []
    assert getattr(result, "resolved", None) is True, (
        "an empty wmbts: list must still report the binding as RESOLVED, so the "
        "caller can tell 'no decomposition' from 'could not resolve'"
    )


def test_each_returned_wmbt_resolves_to_its_yaml_path(bound, no_gh) -> None:
    """The caller must be able to render more than a bare URN."""
    root, _store = bound

    result = _resolver()(_ISSUE, control_root=root)
    paths = getattr(result, "paths", None)

    assert paths, "the resolver returned URNs with no way to locate their YAML"
    for urn in (FEATURE_WMBT, _SECOND_WMBT):
        assert urn in paths, f"no path resolved for {urn}"
