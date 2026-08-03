# URN: test:govern-lifecycle:bind-issue-feature:L003-UNIT-002-unresolvable-binding-is-reported-not-blank
# Acceptance: acc:govern-lifecycle:L003-UNIT-002-unresolvable-binding-is-reported-not-blank
# WMBT: wmbt:govern-lifecycle:L003
# Phase: RED
# Layer: presentation
# Runtime: python
# Assertion: behavioral
# Purpose: An issue with no binding, or a binding naming a feature plan/ does not contain, is a distinct outcome and never renders as the "none found" an undecomposed issue produces.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:L003-UNIT-002-unresolvable-binding-is-reported-not-blank
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:L003

Purpose: close the silent-blank failure mode at its source.

"WMBTs: none found" is what `atdd coach enter` prints for a well-decomposed
issue, an undecomposed issue, an unbound issue and a broken lookup alike. One
string for four states is why the defect read as a decomposition gap for so
long. The three failure states must be separable programmatically, not only by
reading the message.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    ABSENT_FEATURE_URN,
    FEATURE_URN,
    control_root,
    open_store,
    optional_attr,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_RESOLVER_MODULE = "atdd.coach.commands.issue_feature_binding"
_RESOLVER_ATTR = "resolve_wmbts_for_issue"
_RENDER_ATTR = "render_wmbt_section"

UNBOUND = 97001      # stored feature is None
UNRESOLVED = 97002   # feature URN absent from plan/
EMPTY = 97003        # feature resolves, declares no WMBTs

_NONE_FOUND = "none found"


def _attr(name):
    fn = optional_attr(_RESOLVER_MODULE, name)
    assert fn is not None, f"expected {_RESOLVER_MODULE}.{name}"
    return fn


@pytest.fixture()
def seeded(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root, wmbts=())
    store = open_store(root)
    seed_issue(store, slug="unbound", issue_number=UNBOUND, feature=None)
    seed_issue(store, slug="unresolved", issue_number=UNRESOLVED, feature=ABSENT_FEATURE_URN)
    seed_issue(store, slug="empty", issue_number=EMPTY, feature=FEATURE_URN)
    return root


def test_a_null_binding_yields_an_explicit_unbound_outcome(seeded) -> None:
    result = _attr(_RESOLVER_ATTR)(UNBOUND, control_root=seeded)

    assert getattr(result, "resolved", None) is False
    assert getattr(result, "reason", None) == "unbound", (
        "an issue carrying no feature binding must report 'unbound', not an empty list"
    )


def test_an_absent_feature_yields_an_explicit_unresolved_outcome(seeded) -> None:
    result = _attr(_RESOLVER_ATTR)(UNRESOLVED, control_root=seeded)

    assert getattr(result, "resolved", None) is False
    assert getattr(result, "reason", None) == "unresolved"
    assert ABSENT_FEATURE_URN in str(getattr(result, "detail", "")), (
        "the unresolved outcome does not name the URN that failed to resolve"
    )


def test_the_three_outcomes_are_programmatically_distinguishable(seeded) -> None:
    """A caller must separate them without parsing message text."""
    resolve = _attr(_RESOLVER_ATTR)
    outcomes = {
        n: (getattr(r, "resolved", None), getattr(r, "reason", None))
        for n, r in (
            (UNBOUND, resolve(UNBOUND, control_root=seeded)),
            (UNRESOLVED, resolve(UNRESOLVED, control_root=seeded)),
            (EMPTY, resolve(EMPTY, control_root=seeded)),
        )
    }
    assert len(set(outcomes.values())) == 3, (
        f"the three states collapse to fewer than three distinct outcomes: {outcomes}"
    )


def test_rendered_output_never_says_none_found_for_a_broken_binding(seeded) -> None:
    """The user-visible half: the string that misinformed for months is gone."""
    render = _attr(_RENDER_ATTR)

    for number, expected in ((UNBOUND, "binding"), (UNRESOLVED, "resolve")):
        text = str(render(_attr(_RESOLVER_ATTR)(number, control_root=seeded)))
        assert _NONE_FOUND not in text.lower(), (
            f"issue #{number} still renders as {_NONE_FOUND!r}, which is "
            "indistinguishable from a genuinely undecomposed issue"
        )
        assert expected in text.lower(), (
            f"the rendered text for issue #{number} does not explain the failure"
        )


def test_a_resolved_but_empty_feature_still_reads_as_undecomposed(seeded) -> None:
    """The one case where 'no WMBTs' is the honest answer."""
    result = _attr(_RESOLVER_ATTR)(EMPTY, control_root=seeded)

    assert getattr(result, "resolved", None) is True
    assert list(getattr(result, "wmbts", [])) == []
