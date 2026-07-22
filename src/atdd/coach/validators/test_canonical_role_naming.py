# URN: component:govern-lifecycle:enforcement-substrate:test_canonical_role_naming:backend:domain
# Runtime: python
# Purpose: Bound validator for role-aware canonical managed-surface naming (issue #865).

"""Coach validator for the role-aware canonical naming rule (issue #865).

Enforces (advisory) ``coach.session.canonical-role-name`` — coach-managed
surface/workspace names match ``<REPO><N>[-phase<M>]-<role>-<slug>`` with
role ∈ {worker, coach-daemon, observer}. This is the "stop the log-theater"
enforcement applied to NAMING: a managed surface whose name lacks the role-aware
shape is flagged for re-application.

Recognition is delegated to the pure domain primitive (single source of truth)
via the recogniser ``atdd.coach.utils.canonical_role_naming`` (rehomed out of the
decommissioned observer_rules package in #1486). The rule is bound here via
``bind_rule`` so the reverse-coherence substrate resolves the convention's
``validator:`` field to this module.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/validators/test_canonical_role_naming.py -v
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.canonical_role_naming import (
    flag_non_conforming,
    is_conforming,
)
from atdd.coach.utils.rule_binding import bind_rule

pytestmark = [pytest.mark.coach]

_RULE = bind_rule("coach.session.canonical-role-name")


def test_managed_surface_names_role_aware():
    """A role-aware managed name passes; a name lacking the role segment is flagged."""
    conforming = "ATDD865-worker-coach-layout"
    drifted = "ATDD865-coach-layout"  # #470 shape, no <role> segment

    assert is_conforming(conforming), (
        f"{conforming!r} should satisfy {_RULE.rule_id}"
    )
    assert not is_conforming(drifted), (
        f"{drifted!r} lacks the <role> segment and must be flagged "
        f"({_RULE.rule_id})"
    )

    events = [
        {"type": "surface_state", "ref": "surface:1", "name": conforming},
        {"type": "surface_state", "ref": "surface:2", "name": drifted},
    ]
    flagged = flag_non_conforming(events)
    assert flagged == ["surface:2"], (
        f"only the non-role-aware managed surface should be flagged; got {flagged}"
    )
