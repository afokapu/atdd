# URN: test:govern-lifecycle:bind-issue-feature:L003-SMOKE-001-coach-enter-lists-plan-backed-wmbts
# Acceptance: acc:govern-lifecycle:L003-SMOKE-001-coach-enter-lists-plan-backed-wmbts
# WMBT: wmbt:govern-lifecycle:L003
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Against the real CLI in a real checkout, `atdd coach enter <N>` lists the WMBTs the plan graph declares for a bound issue.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:L003-SMOKE-001-coach-enter-lists-plan-backed-wmbts
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:L003

Purpose: close the user-visible symptom in the shipped artifact.

The discriminator is a real `gh` on PATH that answers the issue view and
returns `[]` for the atdd-wmbt label query — which is the honest live answer,
since nothing has minted that label since #1477 and the newest such issue is
#1059. Any WMBT in the output therefore came from plan/ and nowhere else.

Making the provider merely ABSENT would not discriminate: `_fetch_sub_issues`
swallows subprocess failure and returns an empty list, so an unreachable `gh`
is indistinguishable from a correct empty answer — and `atdd coach enter`
cannot fetch the issue metadata at all without one, which would fail the test
for an unrelated reason.

Observed on #1635 itself at INIT, PLANNED and RED: "WMBTs: none found", while
the issue carried Y006, C011 and L003 on the plan graph.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._bind_issue_feature_helpers import (
    FEATURE_URN,
    FEATURE_WMBT,
    control_root,
    open_store,
    seed_issue,
    stub_issue,
    write_plan_tree,
    write_stub_gh,
)

pytestmark = [pytest.mark.platform]

_SRC = Path(__file__).resolve().parents[4]

BOUND = 98001
UNBOUND = 98002
_NONE_FOUND = "none found"


def _enter(root: Path, number: int) -> subprocess.CompletedProcess:
    """Run the real `atdd coach enter <N>` against the stub provider."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    env["ATDD_CONTROL_ROOT"] = str(root)
    # The stub `gh` answers issue views and returns [] for the atdd-wmbt label
    # query, so plan/ is the only possible source of a WMBT in the output.
    env["PATH"] = f"{root / 'stub-bin'}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", "atdd", "coach", "enter", str(number)],
        cwd=root, env=env, capture_output=True, text=True, timeout=180,
    )


@pytest.fixture()
def repo(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root, wmbts=(FEATURE_WMBT,))
    store = open_store(root)
    seed_issue(store, slug="bound-probe", issue_number=BOUND, feature=FEATURE_URN)
    seed_issue(store, slug="unbound-probe", issue_number=UNBOUND, feature=None)
    # INIT: `enter` prints context and returns without creating a worktree
    # (`_BRANCH_STATUSES` excludes it), so the WMBT listing is exercised without
    # dragging real git-worktree layout into a lookup test. It is also the exact
    # state in which the symptom was observed on #1626 and #1635.
    write_stub_gh(root, {
        BOUND: stub_issue(BOUND, status="INIT", body=f"| Feature | `{FEATURE_URN}` |"),
        UNBOUND: stub_issue(UNBOUND, status="INIT", body="no Feature row"),
    })
    return root


def test_a_bound_issue_lists_its_wmbt_from_the_plan_graph(repo) -> None:
    result = _enter(repo, BOUND)
    out = (result.stdout or "") + (result.stderr or "")

    assert FEATURE_WMBT in out, (
        f"`atdd coach enter {BOUND}` did not list {FEATURE_WMBT} even though the "
        "issue's feature YAML declares it — this is the symptom observed three "
        f"times on #1635 itself.\n{out}"
    )


def test_the_wmbt_cannot_have_come_from_the_provider(repo) -> None:
    """The provider answered `[]`, so plan/ is the only possible source."""
    result = _enter(repo, BOUND)
    out = (result.stdout or "") + (result.stderr or "")

    assert FEATURE_WMBT in out, (
        "the atdd-wmbt label query returned [] — the live answer — and no WMBT "
        "appeared, so resolution is still provider-backed rather than plan-backed"
    )
    assert _NONE_FOUND not in out.lower(), (
        "the run degraded to the silent empty answer despite a resolvable binding"
    )


def test_an_unbound_issue_reports_the_missing_binding_explicitly(repo) -> None:
    result = _enter(repo, UNBOUND)
    out = ((result.stdout or "") + (result.stderr or "")).lower()

    assert _NONE_FOUND not in out, (
        "an unbound issue still prints 'none found', which is indistinguishable "
        "from a genuinely undecomposed issue"
    )
    assert "binding" in out or "feature" in out, (
        "the output does not explain that the issue carries no feature binding"
    )


def test_reporting_a_missing_binding_does_not_crash_the_enter_path(repo) -> None:
    """A diagnostic must not become an outage."""
    result = _enter(repo, UNBOUND)

    assert result.returncode in (0, 1), (
        f"`atdd coach enter` exited {result.returncode} for an unbound issue; "
        f"reporting a missing binding must not crash the command.\n{result.stderr}"
    )
