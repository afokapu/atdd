# Acceptance: acc:govern-lifecycle:E050-UNIT-004-the-derived-terminal-edge-stays-ungated
"""GT-005 — `REFACTOR->COMPLETE` must stay OUT of `gate.transitions` (#1999 Decision 31).

This test guards an ABSENCE, which is unusual enough to be worth stating plainly: the fix
here is a config line that must never be written, so the only way to hold it is a test that
fails when someone writes it.

WHY. `COMPLETE` is not a decision. The projection contract says *"COMPLETE is NOT storable:
it is DERIVED from merge-to-main"*, and `evidence.check_transition(uid,'REFACTOR','COMPLETE')`
returns `complete_is_derived`. Nothing is authorised at that edge; the authorisation was the
merge, which already happened.

WHAT BREAKS IF IT IS ADDED. `REFACTOR` declares `autonomy: operator`, so `_autonomy_waiver`
does not fire and `ApprovalTokenGateCheck` enforces at transition time. `atdd auto-phase`
runs `atdd coach transition <N> COMPLETE` inside a GitHub Actions checkout, where
`.atdd/runtime/` does not exist (`.gitignore:42`) — `locate_approval_token` finds nothing and
the check fails closed. Every merged PR's phase advance then exits 1: the merge lands the
code and the lifecycle stops at REFACTOR, which is strictly worse than today. The same
position has already failed this way for the adjacent reason — run `34749392023`, where
`SmokeExecutionGateCheck` returned COULD_NOT_CHECK in CI because the State Store is not in
the checkout.

Four review rounds and three proposed carriers (the committed projection, the
`ATDD-Token-Digest` trailer, the `.atdd/evidence/` artifact) were spent trying to get a
signature to that checkout before the premise itself was found to be wrong. This test is the
cheapest possible record of that: the config line is the trap, not the fix.

Convention: src/atdd/coach/conventions/phase_machine.convention.yaml
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.gate.decision import is_transition_gated
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]


def _repo_config() -> dict:
    config_file = Path(find_repo_root()) / ".atdd" / "config.yaml"
    if not config_file.exists():
        pytest.skip("no .atdd/config.yaml in this checkout")
    return yaml.safe_load(config_file.read_text()) or {}


def test_the_merge_edge_is_not_gated_in_this_repo() -> None:
    """The live config must not arm the edge that auto-phase crosses in CI."""
    assert not is_transition_gated(_repo_config(), "REFACTOR", "COMPLETE"), (
        "`REFACTOR->COMPLETE` is gated in .atdd/config.yaml. REFACTOR declares "
        "`autonomy: operator`, so the approval check enforces at transition time — and "
        "`atdd auto-phase` runs that transition on a CI checkout where `.atdd/runtime/` "
        "does not exist. Every post-merge advance will exit 1 and no issue will reach "
        "COMPLETE. COMPLETE is DERIVED from merge-to-main; there is nothing to authorise."
    )


def test_the_default_does_not_gate_it_either() -> None:
    """A consumer repo that configures nothing must inherit the safe answer."""
    assert not is_transition_gated({}, "REFACTOR", "COMPLETE"), (
        "the built-in DEFAULT_GATED_TRANSITIONS now gates REFACTOR->COMPLETE, so every "
        "consumer inherits the CI breakage without writing a line of config."
    )


def test_the_plan_edge_is_still_gated() -> None:
    """The guard above must not be satisfied by gating nothing at all."""
    assert is_transition_gated(_repo_config(), "PLANNED", "RED"), (
        "PLANNED->RED is no longer gated, so the operator's remaining signature is gone. "
        "This test exists to keep one edge ungated, not to disarm the lifecycle."
    )
