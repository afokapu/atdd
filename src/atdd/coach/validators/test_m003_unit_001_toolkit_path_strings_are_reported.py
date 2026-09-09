# URN: test:govern-lifecycle:govern-lifecycle:M003-UNIT-001
# Acceptance: acc:govern-lifecycle:M003-UNIT-001-a-toolkit-path-string-is-reported-not-gated
# WMBT: wmbt:govern-lifecycle:M003
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""M003-UNIT-001 — the shape the strict detector cannot see is reported, never gated.

`coach.source-layout.platform-marker-on-toolkit-selftest` recognises literal Path
division chains. R005-SMOKE-001 evaded it by holding its toolkit path as a plain
string constant handed to a subprocess, and shipped red in every consumer repo
until #1863.

Extending the strict gate to that shape was prototyped and rejected on evidence.
Against this tree it scores ONE true positive in FOUR — the three current matches
all pass in a real non-toolkit repo, because they name a toolkit path used as DATA
(a string classifier's input; a `file:Symbol` citation) rather than a path anything
opens. Telling those apart needs dataflow the AST scan does not do.

The harm is asymmetric, and that is what settles it. A false negative costs one red
test in consumers — visible, diagnosable, fixable, which is exactly what #1863 was.
A false positive puts `pytest.mark.platform` on a validator that works fine there,
silently disabling a live gate in every consumer repo, in the direction nobody
audits. The strict detector's own docstring already names that hazard.

So the blind spot is made VISIBLE instead of enforced. What a class validator
cannot see is otherwise indistinguishable from there being nothing to see, and
that indistinguishability is the actual defect #1865 records.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

RULE_ID = "coach.source-layout.toolkit-path-string-in-unmarked-selftest"


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


def test_m003_unit_001_a_toolkit_path_string_is_reported(tmp_path):
    from atdd.coach.validators.test_platform_marker_on_toolkit_selftests import (
        scan_toolkit_path_strings,
    )

    f = _write(tmp_path, "test_leaky.py", '''
        import subprocess

        VALIDATOR = "src/atdd/coach/validators/test_phase_label_projection_only.py"

        def test_x():
            subprocess.run(["pytest", VALIDATOR])
    ''')

    violations = scan_toolkit_path_strings([f], repo_root=tmp_path)

    assert len(violations) == 1, (
        f"the R005 shape — a toolkit path held as a string constant — was not "
        f"reported: {violations!r}"
    )
    v = violations[0]
    assert v.rule_id == RULE_ID
    assert "test_leaky.py:3" in v.location, (
        f"the report must name the assigning line so a human can triage it "
        f"without re-deriving it; got {v.location!r}"
    )
    assert "src/atdd/coach/validators" in v.detail, (
        "the report does not quote the string it found"
    )


def test_m003_unit_001_the_report_never_fails_a_run(tmp_path):
    """Advisory by construction: the gate must warn and pass, not fail."""
    from atdd.coach.validators.test_platform_marker_on_toolkit_selftests import (
        report_toolkit_path_strings,
    )

    f = _write(tmp_path, "test_leaky.py", '''
        VALIDATOR = "src/atdd/coach/validators/anything.py"

        def test_x():
            assert VALIDATOR
    ''')

    with pytest.warns(UserWarning):
        report_toolkit_path_strings([f], repo_root=tmp_path)
