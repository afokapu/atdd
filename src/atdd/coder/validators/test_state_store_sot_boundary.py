# URN: component:govern-lifecycle:enforcement-substrate:test_state_store_sot_boundary:backend:domain
# Runtime: python
# Purpose: Enforce the operational-state-vs-authored-definition SoT boundary (#1274) — the
#          operational State Store layer must hold no authored-definition artifacts.

"""State Store SoT boundary validator (issue #1274).

Two artifact kinds, two sources of truth (see
``coder.state-store.operational-vs-definition-sot``):

* OPERATIONAL / instance state (work-items, version, runs) -> the State Store is SoT;
  committed YAML is a generated projection.
* AUTHORED DEFINITIONS (convention nodes, relationships, trains, wagons, schemas) ->
  git-versioned source, reviewed-in-PR and shipped; never store-only.

This validator enforces the concrete, load-bearing slice of that boundary: the
operational store layer ``src/atdd/state/`` must contain **no authored-definition
artifacts** — no ``*.convention.yaml``, no ``conventions/`` subtree, no
train/wagon/relationship registries, no author ``*.schema.json``. Definitions
live in their git-source archetype homes; the store layer is operational data +
storage APIs only. (A *derived* index of definitions in the store at runtime is
fine — that's a generated cache, not an authored file under ``state/``.)

Convention node: ``src/atdd/coder/conventions/nodes/coder.state-store.operational-vs-definition-sot.convention.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

import atdd
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


_RULE = bind_rule("coder.state-store.operational-vs-definition-sot")

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
STATE_DIR = ATDD_PKG_DIR / "state"

# Authored-definition artifacts that must NOT live inside the operational store layer.
_DEFINITION_GLOBS = ("*.convention.yaml", "*.schema.json")
_DEFINITION_FILENAMES = frozenset(
    {"_trains.yaml", "_wagons.yaml", "relationships.yaml"}
)
_DEFINITION_DIRNAMES = frozenset({"conventions"})


def _relpath(p: Path) -> str:
    try:
        return str(p.relative_to(ATDD_PKG_DIR.parent))
    except ValueError:
        return str(p)


def scan_state_for_definitions() -> List[Violation]:
    """Authored-definition artifacts found under the operational store layer."""
    violations: List[Violation] = []
    if not STATE_DIR.is_dir():
        return violations

    def _flag(path: Path, what: str) -> None:
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{_relpath(path)}:1",
                detail=(
                    f"authored definition ({what}) lives inside the operational State Store "
                    "layer src/atdd/state/ — definitions are git-source under the archetype "
                    "packages, not the store layer"
                ),
            )
        )

    # A conventions/ subtree anywhere under state/.
    for sub in STATE_DIR.rglob("*"):
        if sub.is_dir() and sub.name in _DEFINITION_DIRNAMES:
            _flag(sub, f"{sub.name}/ definition directory")

    # Definition files by glob / filename.
    for glob in _DEFINITION_GLOBS:
        for f in STATE_DIR.rglob(glob):
            if "__pycache__" in f.parts:
                continue
            _flag(f, f.name)
    for f in STATE_DIR.rglob("*"):
        if f.is_file() and f.name in _DEFINITION_FILENAMES:
            _flag(f, f.name)

    return violations


@pytest.mark.coder
def test_operational_store_holds_no_authored_definitions():
    """SPEC: ``coder.state-store.operational-vs-definition-sot``.

    Given: the operational store layer ``src/atdd/state/``.
    When:  it is scanned for authored-definition artifacts.
    Then:  none exist — definitions live in git-source archetype homes, the store
           layer is operational data + storage APIs only.
    """
    assert_disposition_satisfied(
        validator_id="state_store_sot_boundary_operational_vs_definition",
        violations=scan_state_for_definitions(),
    )
