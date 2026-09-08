# URN: test:govern-lifecycle:live-smoke-attestability:E071-UNIT-002-runner-axis-reports-what-would-execute
# Acceptance: acc:govern-lifecycle:E071-UNIT-001-attestability-classifier-assigns-one-class-per-acceptance
# WMBT: wmbt:govern-lifecycle:E071
# Phase: SMOKE
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""#1814 — the runner axis must report what CI would EXECUTE, not what it names.

#1664's axis 3 answered one question: is the anchored test on a CI path whose job
installs the distribution? Two things it did not ask made the answer optimistic in
opposite directions, and both are asserted here from synthetic inputs — no repo
walk, no test executed.

1. **A test that deselects itself records nothing.** Sixteen SMOKE acceptances are
   anchored by modules gating on ``ATDD_RUN_SMOKE``, which no workflow sets. Eight
   of them sit on installed CI paths, so the job is green, the hook is loaded, and
   no evidence exists — reported as ``ci-can-record``, which is the exact shape of
   a check that certifies without checking.

2. **A target named as a FILE was credited to nobody.** ``attesting_ci_path``
   matched a directory prefix only, so the two ``coach/commands/tests`` files
   #1643 named by path — the move this repository makes when a directory is too
   red to add whole — counted as not run at all.

The gate is deliberately narrower than "has a skipif": ``shutil.which("git") is
None`` guards six SMOKE acceptances and is satisfied on every runner, so a blanket
rule would call three-quarters of the gated population unreachable. An ENVIRONMENT
gate is decidable instead of guessed, because the runner's environment is itself
readable from the workflows.
"""
from __future__ import annotations

from pathlib import Path

from atdd.tester.substrate.ci_runner import (
    CI_RUNS_WITH_HOOK,
    CI_RUNS_WITHOUT_HOOK,
    CI_TEST_OPTS_OUT,
    NOT_RUN_BY_CI,
    ci_env_names,
    ci_runner_verdict,
    skip_env_gates,
)

_ENV_GATED = '''
import os
import pytest

pytestmark = [pytest.mark.skipif(not os.environ.get("ATDD_RUN_SMOKE"), reason="opt-in")]

def test_thing():
    assert True
'''

_TOOL_GATED = '''
import shutil
import pytest

pytestmark = [pytest.mark.skipif(shutil.which("git") is None, reason="needs git")]

def test_thing():
    assert True
'''

_DECORATED = '''
import os
import pytest

@pytest.mark.skipif(os.getenv("ATDD_RUN_SMOKE") != "1", reason="opt-in")
def test_thing():
    assert True
'''

_UNGATED = '''
def test_thing():
    assert True
'''


# --------------------------------------------------------------------------- #
# The reader                                                                    #
# --------------------------------------------------------------------------- #
def test_a_module_level_environment_gate_is_reported() -> None:
    assert skip_env_gates(_ENV_GATED) == {"ATDD_RUN_SMOKE"}


def test_a_per_test_decorator_gate_is_reported_too() -> None:
    """Only ``pytestmark`` is module-wide, but a decorator deselects just the same."""
    assert skip_env_gates(_DECORATED) == {"ATDD_RUN_SMOKE"}


def test_a_gate_on_something_other_than_the_environment_is_not_reported() -> None:
    """The narrowness IS the design — see this module's docstring."""
    assert skip_env_gates(_TOOL_GATED) == set()


def test_an_ungated_module_reports_nothing() -> None:
    assert skip_env_gates(_UNGATED) == set()


def test_a_file_that_does_not_parse_names_no_gate_rather_than_raising() -> None:
    """This walks authored source; a reader that crashes classifies nothing."""
    assert skip_env_gates("def (((") == set()


def test_ci_env_names_merges_every_level_it_finds() -> None:
    workflow = """
name: w
env:
  TOP: "1"
jobs:
  a:
    env:
      JOB: "1"
    steps:
      - run: pytest tests/x
        env:
          STEP: "1"
"""
    assert {"TOP", "JOB", "STEP"} <= ci_env_names({"w.yml": workflow})


# --------------------------------------------------------------------------- #
# The verdict                                                                   #
# --------------------------------------------------------------------------- #
_DIR_TARGET = {"tests/covered": True}
_FILE_TARGET = {"tests/covered/test_named.py": True}
_UNINSTALLED = {"tests/covered": False}
_FILE = Path("tests/covered/test_named.py")


def test_an_installed_path_with_no_gate_runs_with_the_hook() -> None:
    assert ci_runner_verdict([_FILE], _DIR_TARGET, set(), set()) == CI_RUNS_WITH_HOOK


def test_a_target_named_as_a_file_is_credited() -> None:
    """#1643's by-path coverage was invisible to the census before #1814."""
    assert ci_runner_verdict([_FILE], _FILE_TARGET, set(), set()) == CI_RUNS_WITH_HOOK


def test_a_gate_ci_does_not_satisfy_beats_the_install() -> None:
    """Green job, loaded hook, test never ran — that must not read as a run."""
    assert (
        ci_runner_verdict([_FILE], _DIR_TARGET, {"ATDD_RUN_SMOKE"}, set())
        == CI_TEST_OPTS_OUT
    )


def test_a_gate_ci_does_satisfy_does_not_count_against_it() -> None:
    """Set the variable in a job and the verdict flips with no edit to the reader."""
    assert (
        ci_runner_verdict([_FILE], _DIR_TARGET, {"ATDD_RUN_SMOKE"}, {"ATDD_RUN_SMOKE"})
        == CI_RUNS_WITH_HOOK
    )


def test_an_uninstalled_path_still_reports_that_the_hook_is_absent() -> None:
    assert ci_runner_verdict([_FILE], _UNINSTALLED, set(), set()) == CI_RUNS_WITHOUT_HOOK


def test_a_path_no_job_runs_outranks_its_gate() -> None:
    """`not-run-by-ci` first: a gate is only interesting once something runs it."""
    assert ci_runner_verdict([_FILE], {}, {"ATDD_RUN_SMOKE"}, set()) == NOT_RUN_BY_CI


def test_an_acceptance_with_no_anchored_test_is_not_run_by_ci() -> None:
    assert ci_runner_verdict([], _DIR_TARGET, set(), set()) == NOT_RUN_BY_CI
