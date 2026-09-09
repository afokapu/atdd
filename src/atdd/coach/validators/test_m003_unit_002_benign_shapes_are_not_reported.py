# URN: test:govern-lifecycle:govern-lifecycle:M003-UNIT-002
# Acceptance: acc:govern-lifecycle:M003-UNIT-002-prose-citations-and-marked-files-are-not-reported
# WMBT: wmbt:govern-lifecycle:M003
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""M003-UNIT-002 — the advisory stays quiet on everything measured to be benign.

An advisory that reports the benign is noise, and noise is how a report stops
being read by the time it matters. Every shape excluded here was measured against
the live tree and confirmed to pass in a real non-toolkit repo:

  * PROSE — `src/atdd/...` in a docstring or comment. This is why the scan reads
    assignments rather than text: the naive substring rule matched ~42 modules,
    almost all of them prose.
  * CITATIONS — `src/atdd/planner/commands/plan_session.py:PlanSession.author`
    names a location for a human, not a file for the filesystem. Two of the three
    current matches are this shape.
  * ALREADY MARKED — a file carrying pytest.mark.platform is already excluded from
    consumer sweeps; reporting it would be asking for work that is done.
  * SUPPRESSED — a triaged case carrying an inline marker on the assigning line.
    This is what lets the live tree start quiet and speak only for something new.
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


def _scan(files, tmp_path):
    from atdd.coach.validators.test_platform_marker_on_toolkit_selftests import (
        scan_toolkit_path_strings,
    )
    return scan_toolkit_path_strings(files, repo_root=tmp_path)


def test_m003_unit_002_prose_is_not_reported(tmp_path):
    f = _write(tmp_path, "test_prose.py", '''
        """This validator scans src/atdd/coach for something.

        See src/atdd/coach/commands/issue.py for the shape.
        """
        # also src/atdd/planner is mentioned here
        def test_x():
            assert True
    ''')
    assert _scan([f], tmp_path) == [], (
        "a toolkit path mentioned in prose was reported; the naive substring rule "
        "this replaces matched ~42 modules almost entirely on docstrings"
    )


def test_m003_unit_002_a_symbol_citation_is_not_reported(tmp_path):
    f = _write(tmp_path, "test_citation.py", '''
        _LOC = "src/atdd/planner/commands/plan_session.py:PlanSession.author"

        def test_x():
            assert _LOC
    ''')
    assert _scan([f], tmp_path) == [], (
        "a file:Symbol citation was reported as a path — it names a location for "
        "a human, and both current instances of this shape pass in a consumer repo"
    )


def test_m003_unit_002_a_platform_marked_file_is_not_reported(tmp_path):
    f = _write(tmp_path, "test_marked.py", '''
        import pytest

        pytestmark = [pytest.mark.coach, pytest.mark.platform]

        VALIDATOR = "src/atdd/coach/validators/thing.py"

        def test_x():
            assert VALIDATOR
    ''')
    assert _scan([f], tmp_path) == [], (
        "a file already excluded from consumer sweeps was reported, which asks "
        "for work that is already done"
    )


def test_m003_unit_002_an_inline_suppression_is_honoured(tmp_path):
    # Same-line, matching the repo's marker convention: disposition_gate reads
    # the offending line and looks for the marker on it, so a marker on the
    # preceding line is a comment about nothing.
    f = _write(tmp_path, "test_suppressed.py", f'''
        OWN_CODE = "src/atdd/coach/commands/issue.py"  # atdd:suppress({RULE_ID}) classifier input, never opened

        def test_x():
            assert OWN_CODE
    ''')
    assert _scan([f], tmp_path) == [], (
        "an inline suppression on the assigning line was ignored; without it the "
        "live tree cannot start quiet, and a report that is noisy on day one is "
        "ignored by the time it matters"
    )


def test_m003_unit_002_suppression_must_be_on_the_assigning_line(tmp_path):
    """A marker elsewhere in the file must not silence an unrelated assignment."""
    f = _write(tmp_path, "test_elsewhere.py", f'''
        def other():
            pass  # atdd:suppress({RULE_ID}) unrelated

        VALIDATOR = "src/atdd/coach/validators/thing.py"

        def test_x():
            assert VALIDATOR
    ''')
    assert len(_scan([f], tmp_path)) == 1, (
        "a suppression on an unrelated line silenced the assignment; suppression "
        "must be a statement about the site it sits on"
    )
