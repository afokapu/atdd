# URN: test:mediate-worker-decisions:mediate-decision:C008-UNIT-001-bootstrap-cd-prefix-and-repo-graph-auto
# Acceptance: acc:mediate-worker-decisions:C008-UNIT-001-bootstrap-cd-prefix-and-repo-graph-auto
# WMBT: wmbt:mediate-worker-decisions:C008
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C008-UNIT-001 — a coach worker's sanctioned bootstrap is AUTO, not escalated.

A coach-launched worker runs its pre-flight from inside its worktree as a
compound ``cd <worktree> && <read-only command>`` (``atdd gate`` /
``atdd repo graph``). Before #1031 the leading ``cd`` tripped the ``&&``
composition guard so EVERY bootstrap step escalated-by-default with no reply
path, and the worker deadlocked on step one. The fix peels exactly one
``cd <plain-path> &&`` prefix and re-checks the remainder under the full gate,
and adds ``atdd repo graph`` (read-only) to the allowlist.

This pairs with C008-UNIT-002 (the adversarial guard): the unwrap must NOT widen
the #1014 escalate-by-default hole.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    AUTO,
    classify_command,
)

# Sanctioned bootstrap commands a coach worker issues at launch. Each must
# classify AUTO so the worker is never deadlocked on its own pre-flight.
SANCTIONED_BOOTSTRAP_AUTO = [
    "cd /Users/me/Github/atdd/issue-1031 && atdd gate",
    "cd /Users/me/Github/atdd/issue-1031 && atdd repo graph",
    "cd /tmp/wt && atdd repo graph --wagon mediate-worker-decisions",
    "atdd gate",
    "atdd repo graph",
    "atdd repo graph --wagon coach-wave-orchestration",
]


@pytest.mark.parametrize("command", SANCTIONED_BOOTSTRAP_AUTO)
def test_sanctioned_bootstrap_command_is_auto(command):
    assert classify_command(command) == AUTO, (
        f"{command!r} is a sanctioned read-only bootstrap step and must classify "
        "AUTO — escalating it deadlocks the worker (no reply path, #1031)"
    )
