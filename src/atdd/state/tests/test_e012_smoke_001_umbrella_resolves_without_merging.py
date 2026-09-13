"""#1967 SMOKE — an umbrella walks to RESOLVED, live, through the shipped modules.

Not a unit test with the machine stubbed. A subprocess loads the real convention
from disk, builds the real projection, and drives the real `check_transition`
through the whole umbrella story: a work item is minted, decomposes into children,
produces no code, and closes.

It is written so it FAILS if RESOLVED is removed or demoted to a rung, and it was
verified red that way before being trusted — the same discipline #1967's sibling
smoke used. Everything about this change looked correct in isolation; what mattered
was whether the pieces met correctly at runtime, and six copies of the phase
vocabulary had to be reconciled before they did.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

#: What an umbrella honestly produces: a plan, children, an operator sign-off.
#: No test evidence, no implementation diff — that is the whole point.
UMBRELLA_TOKENS = [
    "uid_generated", "body_initialized", "plan_complete",
    "acceptance_or_wmbt_refs", "projection_digest", "operator_token_digest",
]

_DRIVER = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, {src!r})
    from atdd.coach.gate.phase_edges import phase_machine, spine, successor, declared_autonomy
    from atdd.coach.handlers.state_machine import Phase, TRANSITION_TABLE, PLANNED_PATH
    from atdd.state.evidence import ESCAPES, RESUMABLE_ESCAPES, PHASE_LADDER, check_transition
    from atdd.state.projection import PHASES
    import atdd.coach.gate.phase_edges as pe

    tokens = set({tokens!r})
    out = {{}}

    # the umbrella closes without a merge and without a single test
    out["init_to_resolved"] = [v.clause for v in
        check_transition("wi_umbrella", "INIT", "RESOLVED", tokens)]
    out["planned_to_resolved"] = [v.clause for v in
        check_transition("wi_umbrella", "PLANNED", "RESOLVED", tokens)]

    # and it stays closed
    out["resolved_to_red"] = [v.clause for v in
        check_transition("wi_umbrella", "RESOLVED", "RED", tokens)]
    out["resumable"] = "RESOLVED" in RESUMABLE_ESCAPES

    # the delivery ladder is untouched, live
    out["spine"] = list(spine())
    out["ladder"] = list(PHASE_LADDER)
    out["planned_path"] = [p.value for p in PLANNED_PATH]
    out["init_successor"] = successor()["INIT"]
    out["unevidenced_green"] = [v.clause for v in
        check_transition("wi_child", "PLANNED", "GREEN", tokens)]

    # every vocabulary that must agree, does
    out["escapes"] = sorted(ESCAPES)
    out["escapes_single_source"] = pe.ESCAPES is __import__(
        "atdd.state.evidence", fromlist=["ESCAPES"]).ESCAPES
    out["phase_enum"] = sorted(p.value for p in Phase)
    out["projection_phases"] = sorted(PHASES)
    out["convention_phases"] = sorted(phase_machine())
    out["resolved_terminal"] = TRANSITION_TABLE[Phase("RESOLVED")] == set()
    out["resolved_autonomy"] = declared_autonomy("RESOLVED")
    print(json.dumps(out))
""")


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    repo = tmp_path_factory.mktemp("smoke-1967")
    src = str(Path(__file__).resolve().parents[3])  # .../src
    driver = repo / "driver.py"
    driver.write_text(_DRIVER.format(src=src, tokens=UMBRELLA_TOKENS))
    proc = subprocess.run([sys.executable, str(driver)], cwd=repo,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"live run failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_an_umbrella_closes_without_tests_or_a_merge(live):
    assert live["init_to_resolved"] == []
    assert live["planned_to_resolved"] == []


def test_a_resolved_umbrella_does_not_come_back(live):
    assert live["resolved_to_red"] == ["terminal_phase"]
    assert live["resumable"] is False


def test_the_delivery_ladder_is_untouched(live):
    ladder = ["INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"]
    assert live["spine"] == ladder
    assert live["planned_path"] == ladder
    assert live["ladder"] == ladder
    assert live["init_successor"] == "PLANNED"
    assert live["unevidenced_green"], "an unevidenced GREEN must still be refused"


def test_resolved_is_a_declared_terminal_escape(live):
    assert "RESOLVED" in live["escapes"]
    assert live["resolved_terminal"] is True
    # null like every terminal: the axis governs the FORWARD edge, which a
    # terminal has none of. Entering it is gated by the evidence policy.
    assert live["resolved_autonomy"] is None


def test_every_phase_vocabulary_agrees(live):
    """Six copies had to be reconciled. This is what keeps them that way."""
    assert live["escapes_single_source"] is True
    assert "RESOLVED" in live["phase_enum"]
    assert "RESOLVED" in live["projection_phases"]
    assert "RESOLVED" in live["convention_phases"]
    assert set(live["phase_enum"]) == set(live["convention_phases"])
