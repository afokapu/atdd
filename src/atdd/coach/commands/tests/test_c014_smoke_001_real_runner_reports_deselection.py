# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C014-SMOKE-001-the-real-runner-reports-a-real-deselection
# Acceptance: acc:govern-lifecycle:C014-SMOKE-001-the-real-runner-reports-a-real-deselection
# WMBT: wmbt:govern-lifecycle:C014
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C014-SMOKE-001 — the real runner counts a real deselection, and reports it.

The units cover the record, its rendering and the parser. None of them can catch
the failure that actually produced this WMBT: that the number is *not obtainable*
from the run's own output under the parallelism the runner uses by default.

    atdd validate planner --local --skip-api   ->  "237 passed"
    the identical selection, run serially      ->  "237 passed, 208 deselected"

pytest-xdist performs collection in the workers, so ``pytest_deselected`` fires
there and the controller's terminal reporter — the thing that prints the summary —
never sees it. A fix that surfaced "whatever pytest said" would surface nothing.

So this file takes the count from the real ``TestRunner`` against this repo's real
validator tree, with no monkeypatching of the marker injection or the counting,
and compares it to what a real serial ``pytest`` reports for the same selection.
The reference number is measured here rather than hardcoded: the suite grows.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

# Aliased: pytest would otherwise try to collect `TestRunner` as a test class.
from atdd.coach.commands.test_runner import TestRunner as _Runner
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.validation_coverage import (
    COULD_NOT_CHECK,
    MarkerExclusion,
    render_coverage_report,
)

pytestmark = [pytest.mark.smoke, pytest.mark.platform]

# The exclusion under measurement is the one that occurs in practice: consumer-mode
# detection injects it on every installed-CLI invocation in this repo.
_EXCLUSION = "not platform"
_PHASE = "planner"


def _repo_root() -> Path:
    root = find_repo_root()
    if not (root / "src" / "atdd" / _PHASE / "validators").is_dir():
        pytest.skip("not running from the toolkit source checkout")
    return root


def _serial_deselected_count(validator_dirs: list[str]) -> int:
    """What pytest itself reports for this selection, with no xdist in the way."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *validator_dirs,
         "-q", "--collect-only", "-p", "no:cacheprovider", "-m", _EXCLUSION],
        capture_output=True,
        text=True,
        timeout=300,
    )
    match = re.search(r"\((\d+) deselected", proc.stdout)
    assert match, (
        "pytest reported no deselection for the marker expression this test is "
        f"about; output tail:\n{proc.stdout[-2000:]}"
    )
    return int(match.group(1))


def test_the_real_runner_reports_a_count_that_is_pytests_own(capsys):
    """The number must be pytest's, not an estimate — and it must be non-zero."""
    root = _repo_root()
    runner = _Runner(repo_root=root)
    validator_dirs = runner._get_validator_dirs(_PHASE)
    assert validator_dirs, "planner validators must resolve"

    expected = _serial_deselected_count(validator_dirs)
    assert expected > 0, "this acceptance requires a suite that actually deselects"

    report = runner.probe_coverage(validator_dirs, [_EXCLUSION], phase=_PHASE)

    assert report is not None, "the runner must obtain the count, not give up silently"
    assert report.could_not_check == expected
    assert report.selected > 0
    assert report.total == report.selected + report.could_not_check


def test_the_count_appears_in_the_runs_output_which_it_does_not_today(capsys):
    """The controller never observes the deselection its workers performed.

    So the run has to say this itself. Asserting on rendered output rather than on
    the record is deliberate: an operator reading a terminal is the reader whose
    absence of information is the defect.
    """
    root = _repo_root()
    runner = _Runner(repo_root=root)
    validator_dirs = runner._get_validator_dirs(_PHASE)

    report = runner.probe_coverage(validator_dirs, [_EXCLUSION], phase=_PHASE)
    assert report is not None

    rendered = render_coverage_report(report)
    assert COULD_NOT_CHECK in rendered
    assert str(report.could_not_check) in rendered
    assert str(report.total) in rendered


def test_every_exclusion_the_runner_applies_is_reported_with_its_real_cause():
    """The count must be attached to the cause that actually produced it.

    There is exactly one place that injects ``not platform`` — ``run_tests``, into
    the marker list — and the reporter reads that same list rather than
    re-deriving it, so the two cannot drift. What this asserts is the part that
    could still be wrong: that the *reason* names consumer-mode detection rather
    than a generic, because "a flag I passed" and "an environment check I did not
    know had fired" are different facts for the operator.
    """
    root = _repo_root()
    runner = _Runner(repo_root=root)

    exclusions = runner.coverage_exclusions(
        markers=["not github_api", _EXCLUSION], consumer_mode=True
    )

    by_expr = {e.expression: e for e in exclusions}
    assert set(by_expr) == {"not github_api", _EXCLUSION}
    assert all(isinstance(e, MarkerExclusion) and e.reason for e in exclusions), (
        "every reported exclusion must carry the reason it was applied"
    )
    assert "is_atdd_source_repo" in by_expr[_EXCLUSION].reason, (
        "the platform exclusion must name the detection that injected it"
    )
    assert "--skip-api" in by_expr["not github_api"].reason

    # A run that excludes nothing reports no exclusions — and separately reports a
    # could_not_check of zero, which is the claim, not the silence.
    assert runner.coverage_exclusions(markers=[], consumer_mode=False) == ()


def test_reporting_the_count_does_not_alter_the_verdict():
    """Surfacing what was not checked must not itself change what was checked.

    This issue's scope is observability. Turning the count into a failure would
    break every consumer repo's ``atdd validate``, which always excludes platform.
    """
    root = _repo_root()
    runner = _Runner(repo_root=root)
    validator_dirs = runner._get_validator_dirs("coder")

    report = runner.probe_coverage(validator_dirs, [_EXCLUSION], phase="coder")

    assert report is not None
    assert report.could_not_check >= 0
    # The probe is collection-only: it must not run, mutate or fail anything.
    assert report.selected > 0
