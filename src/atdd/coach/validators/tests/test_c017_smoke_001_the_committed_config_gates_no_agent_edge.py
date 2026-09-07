# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C017-SMOKE-001-the-committed-config-gates-no-agent-edge
# Acceptance: acc:govern-lifecycle:C017-SMOKE-001-the-committed-config-gates-no-agent-edge
# WMBT: wmbt:govern-lifecycle:C017
# Phase: RED
# Layer: integration
"""C017-SMOKE-001 — the repository's own committed config and machine agree.

Reads the real `.atdd/config.yaml` and `phase_machine.convention.yaml` from disk,
not fixtures, because config drift lands in the committed files and nowhere else.
A synthetic table cannot catch someone re-adding a gate here.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import is_atdd_source_repo

from ._c017_gate_autonomy import gate_transitions, operator_gated_agent_edges
from ._d020_autonomy import phases


@pytest.mark.platform
def test_the_committed_config_gates_no_agent_edge():
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; the committed config is the subject")

    declared = phases()
    configured = gate_transitions()
    assert configured, ".atdd/config.yaml declares no gate.transitions to check"

    offenders = operator_gated_agent_edges(declared, configured)

    assert offenders == [], (
        "gate.transitions gates edge(s) the phase machine declares agent-submittable, "
        f"so the lifecycle stops on a human the convention did not ask for: {offenders}. "
        "Either drop the edge from gate.transitions, or change the phase's declared "
        "autonomy — the two files must say the same thing."
    )
