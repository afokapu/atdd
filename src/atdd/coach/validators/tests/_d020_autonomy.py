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
}

#: The nine phases, sorted — the shape both the in-repo and consumer probes expect.
EXPECTED_PHASES = sorted(PINNED)

#: The conventions snapshot hash measured on 2026-07-26, BEFORE the autonomy axis
#: was authored, via load_conventions(repo_root).snapshot_hash.
#:
#: PhaseSpec does not read `autonomy` and _normalized_snapshot derives the hash
#: from PhaseSpec, so declaring the axis cannot move it. Projecting the axis onto
#: PhaseSpec — which a mechanical submitter check will need — WILL move it, and
#: the assertions guarding this constant are the tripwire for that.
PRE_CHANGE_SNAPSHOT_HASH = (
    "88af3062dfd486ee0d206946e82bebe408a3718873673f11bc0960f14e4e0913"
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
