# URN: component:govern-lifecycle:define-transition-autonomy:d020_autonomy:backend:unit
# Runtime: python
# Purpose: Shared fixtures for the D020 transition-autonomy acceptances (#1626).

"""Constants and readers shared by the five D020 acceptance test files.

Each of those files asserts a different property of the SAME two artifacts — the
phase machine and the transition-autonomy convention node — so the paths, the
pinned table and the pre-change snapshot hash were duplicated across three to
five modules. A single definition means a future edit to the axis cannot leave
one file asserting against a stale copy of the truth.

Leading underscore so pytest does not collect it, matching ``_wheel_harness``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from atdd.coach.utils.repo import find_repo_root

#: The phase machine, relative to the repo root.
MACHINE_REL = Path("src/atdd/coach/conventions/phase_machine.convention.yaml")

#: The convention node stating the principle the axis encodes.
NODE_REL = Path(
    "src/atdd/coach/conventions/nodes/coach.lifecycle.transition-autonomy.convention.yaml"
)

#: The autonomy table pinned by the operator on #1626, keyed by phase.
#:
#: `operator` reserves the forward transition for a human sign-off, `agent` lets
#: the phase's own persona submit it unattended, and None marks a phase with no
#: forward transition. PLANNED is `operator` because it is the sole member of
#: gate.decision.DEFAULT_GATED_TRANSITIONS; REFACTOR because auto-phase cannot
#: verify a modified artifact post-merge (#1611).
PINNED: Dict[str, Any] = {
    "INIT": "operator",
    "PLANNED": "operator",
    "RED": "agent",
    "GREEN": "agent",
    "SMOKE": "agent",
    "REFACTOR": "operator",
    "COMPLETE": None,
    "BLOCKED": "operator",
    "OBSOLETE": None,
    # #1967. Terminal, so null like COMPLETE and OBSOLETE: the axis is about the
    # FORWARD edge, and a terminal has none. Entering it is an operator decision,
    # enforced by the evidence policy rather than by this key.
    "RESOLVED": None,
}

#: The declared phases, sorted — the shape both the in-repo and consumer probes
#: expect. Grew to ten with RESOLVED (#1967); it is a count of PINNED, not a
#: literal, so the next phase does not have to re-edit a number in prose.
EXPECTED_PHASES = sorted(PINNED)

#: The conventions snapshot hash. Measured 2026-07-26 BEFORE the autonomy axis was
#: authored, re-measured 2026-09-13 when #1967 added the RESOLVED phase.
#:
#: What it guards is unchanged: PhaseSpec does not read `autonomy`, and
#: _normalized_snapshot derives the hash from PhaseSpec, so DECLARING the axis
#: cannot move it. Projecting the axis ONTO PhaseSpec would, and that is still the
#: tripwire. Adding a PHASE also moves it — legitimately, because the PhaseSpec set
#: itself grew — so the value was re-baselined rather than the assertion relaxed.
#: A move with no phase added and no axis projected is still the alarm it always was.
PRE_CHANGE_SNAPSHOT_HASH = (
    "b79c3d11b8350dfd89098a769afb268c8ac7f85d104ba9f89136731f5e5ad71a"
)


def machine_data() -> dict:
    """The whole phase-machine document, parsed from the checkout."""
    return yaml.safe_load(
        (find_repo_root() / MACHINE_REL).read_text(encoding="utf-8")
    ) or {}


def phases() -> dict:
    """Just the ``phases:`` mapping, asserted non-empty."""
    found = machine_data().get("phases") or {}
    assert found, f"{MACHINE_REL} declares no phases"
    return found


def node_prose(node: dict) -> str:
    """Every free-text field of a convention node, joined for substring checks."""
    return " ".join(
        [
            str(node.get("statement", "")),
            str(node.get("rationale", "")),
            str(node.get("notes", "")),
        ]
        + [str(term.get("text", "")) for term in (node.get("terms") or [])]
    )
