# URN: test:consolidate-coach-workspace:canonical-coach-surface:Y001-UNIT-001-canonical-coach-tab-name-is-invariant
# Acceptance: acc:consolidate-coach-workspace:Y001-UNIT-001-canonical-coach-tab-name-is-invariant
# WMBT: wmbt:consolidate-coach-workspace:Y001
# Phase: RED
# Layer: domain
# Runtime: python
# Assertion: behavioral
"""Y001-UNIT-001 — ``session_naming`` exposes a canonical coach orchestration
tab-name helper that is invariant across issue numbers and embeds no issue
number.

RED: ``session_naming.py`` only knows per-issue surface names
(``compute_issue_surface_name`` → ``ATDD730``). There is no singular,
issue-number-free coach orchestration tab name, so N coach invocations make N
tabs. This test pins ``compute_coach_surface_name`` — a helper that returns the
same ``ATDD-coach`` string no matter which issue context calls it.
"""
from __future__ import annotations

import re

import pytest

pytestmark = [pytest.mark.platform]


def test_canonical_coach_tab_name_is_invariant():
    """The canonical coach tab name is identical across issue contexts and
    carries no issue number."""
    from atdd.coach.utils import session_naming

    fn = getattr(session_naming, "compute_coach_surface_name", None)
    assert fn is not None, (
        "session_naming.compute_coach_surface_name is not implemented — the "
        "canonical coach orchestration tab-name helper is missing (RED)"
    )

    # An .atdd config dict resolving repo short-name ATDD.
    config = {"repo": {"short_name": "ATDD"}}

    # Called once per issue context — issue #736 and an arbitrary other, #601.
    name_736 = fn(config, 736)
    name_601 = fn(config, 601)

    assert name_736 == name_601, (
        f"canonical coach tab name varies with issue context "
        f"({name_736!r} for #736 vs {name_601!r} for #601) — it must be singular"
    )
    assert "736" not in name_736 and "601" not in name_736, (
        f"canonical coach tab name {name_736!r} embeds an issue number — "
        f"N issues would still produce N distinct tab names"
    )
    assert not re.match(r"^ATDD-coach-\d+$", name_736), (
        f"{name_736!r} matches the per-issue `ATDD-coach-<N>` form — "
        f"expected the issue-number-free canonical form"
    )
    assert name_736 == "ATDD-coach", (
        f"expected the documented canonical coach tab name 'ATDD-coach', "
        f"got {name_736!r}"
    )
