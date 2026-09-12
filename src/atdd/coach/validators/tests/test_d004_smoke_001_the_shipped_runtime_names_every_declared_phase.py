# URN: test:drive-state-machine:coach-state-machine-and-runtime:D004-SMOKE-001-the-shipped-runtime-names-every-declared-phase
# Acceptance: acc:drive-state-machine:D004-SMOKE-001-the-shipped-runtime-names-every-declared-phase
# WMBT: wmbt:drive-state-machine:D004
# Phase: RED
# Layer: backend.smoke
# Assertion: behavioral
"""D004-SMOKE-001 — in the artifact a consumer installs, the runtime names every phase.

Real infrastructure: the wheel built from this tree, unpacked, imported by a
SEPARATE process with NO source tree on the path. Nothing monkeypatched, no
convention hand-built.

WHY A WHEEL AND NOT THIS CHECKOUT. The unit coverage runs in-tree, and
``phase_edges.PHASE_MACHINE_PATH`` resolves relative to the imported package —
so an in-tree probe reads the worktree and would pass even if the projection
never shipped. That is the exact miss #1474/#1602 were filed for: a convention
YAML that exists in the tree but is not package data. Here the claim is about
the installed artifact, so the wheel is the only honest subject.

WHAT IT WOULD HAVE CAUGHT. #1946 is two Phase enums that compare equal by value,
so every in-process assertion short of identity passes. A consumer installing
the wheel and calling ``Phase("OBSOLETE")`` gets ``ValueError`` — on a phase the
same wheel's own convention declares, and whose ``atdd:OBSOLETE`` GitHub label
the same wheel derives.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]


_PROBE = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import yaml

    from atdd.coach.gate.phase_edges import PHASE_MACHINE_PATH, phase_machine
    from atdd.coach.handlers.state_machine import Phase, TRANSITION_TABLE

    declared = phase_machine()

    nameable, unnameable = [], []
    for name in declared:
        try:
            Phase(name)
            nameable.append(name)
        except ValueError:
            unnameable.append(name)

    print(json.dumps({
        "convention_path": str(PHASE_MACHINE_PATH),
        "declared": {k: list(v) for k, v in declared.items()},
        "vocabulary": [p.value for p in Phase],
        "unnameable": unnameable,
        "table": {str(s): sorted(str(d) for d in t) for s, t in TRANSITION_TABLE.items()},
    }))
    """
)


@pytest.fixture(scope="module")
def probe() -> dict:
    """Run the probe against the unpacked wheel, with the source tree off the path."""
    from ._wheel_harness import extracted_wheel_root

    root = extracted_wheel_root()
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(root), "HOME": str(root)},
    )
    if result.returncode != 0:
        pytest.fail(
            "the shipped package could not be probed — the runtime could not even "
            f"import its own phase machine:\n{result.stderr}"
        )
    return json.loads(result.stdout)


def test_the_shipped_convention_is_the_one_the_process_read(probe) -> None:
    """Guards the test itself: a probe that read the checkout proves nothing."""
    assert "site-packages" not in probe["convention_path"]
    assert str(pytest.__file__).rsplit("/", 2)[0] not in probe["convention_path"]
    assert probe["declared"], "the shipped wheel declares no phases"


def test_every_declared_phase_is_nameable_by_the_shipped_runtime(probe) -> None:
    """The consumer-facing form of #1946."""
    assert probe["unnameable"] == [], (
        f"the shipped convention declares {probe['unnameable']} but the shipped "
        "coach runtime raises ValueError on them — a phase added to the YAML is "
        "invisible to the installed runtime"
    )


def test_the_shipped_runtime_carries_no_undeclared_phase(probe) -> None:
    """The other direction: MERGED is in the wheel's enum and in no convention."""
    extra = sorted(set(probe["vocabulary"]) - set(probe["declared"]))
    assert extra == [], (
        f"the shipped runtime carries {extra}, which its own convention does not "
        "declare; the wheel ships a phase no label, gate or projection admits"
    )


def test_the_shipped_transition_table_matches_the_declared_edges(probe) -> None:
    """Both directions, in the artifact rather than the checkout."""
    expected = {name: sorted(targets) for name, targets in probe["declared"].items()}
    assert probe["table"] == expected


def test_the_wheel_actually_ships_the_convention() -> None:
    """A projection is only as real as the data file it projects from."""
    from ._wheel_harness import wheel_members

    rel = "atdd/coach/conventions/phase_machine.convention.yaml"
    assert rel in wheel_members(), (
        f"{rel} is not in the built wheel; the runtime would have nothing to "
        "project from and every phase question would fail closed"
    )
