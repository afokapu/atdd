# URN: test:govern-lifecycle:freeze-coach-core-typed-api-and-phase-machine:E035-UNIT-003-the-convention-names-the-python-edit-it-costs
# WMBT: wmbt:govern-lifecycle:E035
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""The convention must not advertise a cost lower than the one it charges (#1975).

`phase_machine.convention.yaml` claimed twice that adding a phase needs "no
Coach-core code change (§4.3 property 4)". #1946 made most of that true — the
transition table, `PLANNED_PATH`, the spine successor maps and the `atdd:<PHASE>`
label set all became projections of the YAML — and left one part false: the
VOCABULARY is still a Python literal, the members of `core.types.Phase`.

The claim had already been reasoned from. #1950 quoted it verbatim while rejecting
an EXPERIMENT phase; its conclusion survived, its stated reasoning did not.

WHY THIS TEST AND NOT A COMMENT. The prose and the design can drift again, in
either direction, and nothing noticed the first time. So the assertion is
CONDITIONAL on the design rather than on a fixed string: *while* the enum is a
hand-written literal, the convention must say so. If someone later derives the
enum — making the original claim true again — the premise below stops holding and
this test tells them to delete the qualification rather than leave a second stale
promise behind. It fails on either side of the drift.

It is deliberately NOT anchored to `acc:...E035-UNIT-002-phase-machine-yaml-is-canonical`:
that acceptance still requires scanning CLAUDE.md, which #1941 deleted, so
claiming to satisfy it would be its own false claim.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.gate.phase_edges import PHASE_MACHINE_PATH

pytestmark = [pytest.mark.coach]

#: The literal the convention still depends on, as a reader would have to find it.
_ENUM_DOTTED = "core.types.Phase"

#: The promise #1946 falsified. It may appear only alongside its retraction.
_FALSIFIED = "no Coach-core code change"

#: What marks that promise as history rather than guidance.
_RETRACTION = "corrected in #1975"


@pytest.fixture(scope="module")
def convention_text() -> str:
    if not PHASE_MACHINE_PATH.is_file():
        pytest.fail(f"the phase machine is missing: {PHASE_MACHINE_PATH}")
    return PHASE_MACHINE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def enum_is_a_literal(tmp_path_factory) -> bool:
    """True when `core.types.Phase` does NOT track the convention by itself.

    Measured, not assumed: extend a disposable copy of the machine and ask whether
    the enum grew a member. This is the premise the assertions below hang on, so it
    is established rather than asserted.
    """
    from atdd.coach.core.types import Phase

    data = yaml.safe_load(PHASE_MACHINE_PATH.read_text(encoding="utf-8"))
    data["phases"]["DISCOVERY"] = {
        "agent": None, "transitions_to": ["PLANNED"], "autonomy": None,
    }
    copy: Path = tmp_path_factory.mktemp("pm") / "phase_machine.convention.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    # The enum is derived only if it reflects a machine it was never rebuilt from.
    return "DISCOVERY" not in {member.value for member in Phase}


def test_the_enum_is_still_a_literal(enum_is_a_literal) -> None:
    """The premise, stated so a future reader sees which branch they are in.

    If this ever fails, `core.types.Phase` has become a projection and the
    convention's original "no Coach-core code change" promise is true again — at
    which point the qualification this issue added should be REMOVED, not kept.
    """
    assert enum_is_a_literal, (
        "core.types.Phase now tracks the convention on its own. The cost this "
        "convention documents is stale in the other direction: delete the "
        "qualification added by #1975 rather than leave a second false promise"
    )


def test_the_convention_names_the_enum_it_still_costs(convention_text, enum_is_a_literal) -> None:
    """While the enum is a literal, the convention must name it."""
    assert enum_is_a_literal, "premise checked by the test above"
    assert _ENUM_DOTTED in convention_text, (
        f"phase_machine.convention.yaml never names {_ENUM_DOTTED}, but adding a "
        "phase still costs one line there. A reader planning a lifecycle change "
        "will budget a YAML edit and discover the rest at import time — which is "
        "how #1950 came to quote a cost of zero"
    )


def test_the_convention_does_not_repeat_the_falsified_promise(convention_text, enum_is_a_literal) -> None:
    """The exact sentence #1946 falsified must not survive unqualified.

    Matched against the WHOLE document, not line by line: the YAML block scalar
    wraps prose at ~78 columns, so the promise and the marker that retracts it
    routinely land on different lines. A per-line check reports a false positive
    on correctly-corrected text — it did, on the first run of this test.
    """
    assert enum_is_a_literal, "premise checked above"
    if _FALSIFIED in convention_text:
        assert _RETRACTION in convention_text, (
            f"the convention still promises {_FALSIFIED!r} and nowhere marks it "
            f"corrected (looked for {_RETRACTION!r}). #1946 falsified that promise; "
            "it may appear only as history, never as live guidance"
        )


def test_the_convention_names_a_guard_a_reader_can_run(convention_text) -> None:
    """A claim about cost is only checkable if it says what checks it."""
    assert "D004" in convention_text, (
        "the convention states a cost but names no guard, so a reader cannot "
        "verify it or discover that forgetting the enum line fails closed"
    )
