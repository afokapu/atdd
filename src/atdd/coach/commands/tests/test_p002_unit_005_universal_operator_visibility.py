# URN: test:observe-and-correct:observer-runtime-and-rules:P002-UNIT-005-universal-operator-visibility
# Acceptance: acc:observe-and-correct:P002-UNIT-005-universal-operator-visibility
# WMBT: wmbt:observe-and-correct:P002
# Phase: RED
# Layer: presentation
"""P002-UNIT-005 — operator-visibility must be universal.

Issue #713 OBSINPUT-006 (parallels #695 co-spawn parity): the
operator-visible status line of OBSINPUT-005 must hold for EVERY
observer-bearing entry point — observers co-spawned with the planner,
tester, coder and reviewer personas, AND coach-side monitoring — by the
same shared mechanism. No entry point may be headless.

This is a table-driven test enumerating the observer-bearing entry
points; it fails if any single one lacks the operator-visible line.

RED: fails today — no entry point renders a status line and there is no
shared ``render_status_line`` mechanism.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


# Every observer-bearing entry point: (label, observer_agent_id, persona_id).
# Coach-side monitoring is itself an observer instance and must be visible
# by the same mechanism.
OBSERVER_ENTRY_POINTS = [
    ("planner", "planner-713-aa-observer", "planner-713-aa"),
    ("tester", "tester-713-bb-observer", "tester-713-bb"),
    ("coder", "coder-713-cc-observer", "coder-713-cc"),
    ("reviewer", "reviewer-713-dd-observer", "reviewer-713-dd"),
    ("coach-monitor", "coach-713-ee-observer", "coach-713-ee"),
]


@pytest.mark.parametrize(
    "label,observer_id,persona_id",
    OBSERVER_ENTRY_POINTS,
    ids=[ep[0] for ep in OBSERVER_ENTRY_POINTS],
)
def test_every_observer_bearing_entry_point_is_operator_visible(
    tmp_path: Path, capsys, label: str, observer_id: str, persona_id: str
):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text(f"{label} persona output\n")

    rc = observer.cmd_run(
        agent_id=observer_id,
        runtime_dir=runtime,
        rules_dir=rules_dir,
        once=True,
    )
    assert rc == 0
    out = capsys.readouterr().out

    assert persona_id in out, (
        f"observer-bearing entry point '{label}' is headless — every "
        f"observer instance must render the operator-visible status line"
    )


def test_status_line_is_rendered_by_one_shared_mechanism():
    from atdd.coach.commands import observer

    render = getattr(observer, "render_status_line", None)
    assert render is not None, (
        "a single shared render_status_line mechanism must exist so every "
        "observer-bearing entry point is visible by the same means (#713 "
        "OBSINPUT-006)"
    )
