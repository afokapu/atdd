# Phase: SMOKE
# Layer: e2e
# Assertion: behavioral
"""#1602 SMOKE — the whole chain, through the real path, in both directions.

Everything else in this issue is tested against a seam. This file is the only
proof that the seams are connected, and it is deliberately the least mocked
thing in the change: it builds a real git repository with a real ``plan/``
declaring a real ``execution_kind: live_smoke`` acceptance, runs **pytest in a
subprocess** over it, and then asks the real ``SmokeExecutionGateCheck`` what it
thinks. Nothing between the test running and the gate deciding is stubbed —
the attestation that reaches the gate is the one the pytest hook wrote.

    a live-smoke test that RUNS and PASSES  -> attestation written -> gate PASSES
    a live-smoke test that is SKIPPED       -> skip recorded       -> gate FAILS
    a live-smoke test that never runs       -> nothing recorded    -> gate FAILS

The first line is the negative control and it is the one that matters. A gate
that refuses everything satisfies the other two and is worthless — that is the
failure mode this whole issue exists to remove, and reproducing it in the test
suite would be the same mistake one level up.

Two further rows go beyond the brief because the record would otherwise be
decorative: the attestation must actually *carry* what it claims (commit,
execution kind, acceptance urn), and it must go stale — smoke run at commit A
must not license a transition at commit B.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

import atdd
from atdd.coach.gate.decision import GateContext
from atdd.coach.gate.smoke_execution_check import SmokeExecutionGateCheck
from atdd.state.evidence import open_state_store, smoke_executions

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

ISSUE = 1602
SLUG = "smoke-gate-probe"
BRANCH = f"feat/{SLUG}"
ACCEPTANCE_URN = "acc:smoke-gate-probe:live-smoke-executes"

#: The working tree this suite is running from — the subprocess must import the
#: same source, not an installed wheel, or the run would prove nothing about the
#: code under test.
SRC_ROOT = Path(atdd.__file__).resolve().parent.parent

_PROBE_HEADER = f"""\
# Acceptance: {ACCEPTANCE_URN}
\"\"\"The live-smoke probe the acceptance is anchored to.\"\"\"
import time
"""

PROBE_THAT_RUNS = _PROBE_HEADER + """

def test_live_smoke_probe():
    time.sleep(0.05)  # a measurable duration: a 0s "run" is the #1192 tell
    assert True
"""

PROBE_THAT_SKIPS = _PROBE_HEADER + """
import pytest


@pytest.mark.skip(reason="the #1076 failure mode: passing by never executing")
def test_live_smoke_probe():
    time.sleep(0.05)
    assert True
"""

PROBE_WITHOUT_ANCHOR = """\
\"\"\"A test that is not anchored to any live_smoke acceptance.\"\"\"


def test_something_unrelated():
    assert True
"""

WMBT_YAML = f"""\
identity:
  urn: wmbt:smoke-gate-probe:E001
statement: the live-smoke probe executes against real infrastructure
acceptances:
  - identity:
      urn: {ACCEPTANCE_URN}
      phase: SMOKE
    execution_kind: live_smoke
    purpose: the probe runs and its execution is attested
"""


# --------------------------------------------------------------------------- #
# The fixture repository                                                       #
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=probe@atdd.test", "-c", "user.name=probe", *args],
        cwd=str(repo), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout.strip()


def _build_repo(root: Path, probe_source: str) -> Path:
    """A minimal but genuine ATDD repo: git history, plan/, store, probe test."""
    repo = root / "probe-repo"
    (repo / "plan" / "govern_probe").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / ".atdd").mkdir(parents=True)

    (repo / "plan" / "govern_probe" / "E001.yaml").write_text(WMBT_YAML)
    (repo / "tests" / "test_live_smoke_probe.py").write_text(probe_source)
    (repo / "tests" / "test_unanchored.py").write_text(PROBE_WITHOUT_ANCHOR)
    (repo / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    # Pins pytest's rootdir to the fixture repo so the toolkit's own pyproject
    # (and its plugin/marker config) can never leak into the subprocess run.
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")

    _git(repo, "init", "-q", "-b", BRANCH)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "probe repo")

    with open_state_store(control_root=repo) as store:
        store.objects.upsert(SLUG, "work_item", state="SMOKE")
        store.external_refs.link(SLUG, "github", "issue", str(ISSUE))
    return repo


def _run_pytest(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run pytest over the fixture repo in a subprocess, importing OUR source.

    ``ATDD_CONTROL_ROOT``/``ATDD_REPO_ROOT`` pin both resolvers at the fixture
    repo, so the run can neither read nor write the developer's real store.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_ROOT)
    env["ATDD_CONTROL_ROOT"] = str(repo)
    env["ATDD_REPO_ROOT"] = str(repo)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra],
        cwd=str(repo), capture_output=True, text=True, timeout=300, env=env,
    )


def _gate(repo: Path):
    return SmokeExecutionGateCheck().run(GateContext(
        issue_number=ISSUE, from_phase="SMOKE", to_phase="REFACTOR", worktree=repo,
    ))


def _runs(repo: Path):
    with open_state_store(control_root=repo) as store:
        return smoke_executions(store, SLUG)


@pytest.fixture(autouse=True)
def _isolate_control_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep this test's store reads inside tmp_path, never the developer's."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path / "probe-repo"))


# --------------------------------------------------------------------------- #
# Direction 1 — it really ran: the negative control                            #
# --------------------------------------------------------------------------- #


def test_a_live_smoke_run_that_passes_writes_an_attestation_and_opens_the_gate(
    tmp_path: Path,
) -> None:
    """The whole chain, forward: pytest ran -> store recorded -> gate PASSES."""
    repo = _build_repo(tmp_path, PROBE_THAT_RUNS)
    assert not _gate(repo).passed, (
        "the gate was already open before smoke ran — nothing below would mean anything"
    )

    result = _run_pytest(repo)
    assert result.returncode == 0, f"the probe suite failed:\n{result.stdout}\n{result.stderr}"

    runs = _runs(repo)
    assert len(runs) == 1, (
        f"the pytest hook recorded {len(runs)} run(s), expected exactly the anchored "
        f"probe — unanchored tests must not be attested. stdout:\n{result.stdout}"
    )
    assert runs[0].outcome == "passed"
    assert runs[0].duration_s > 0.0, "a run with no measured duration did not execute"
    assert runs[0].nodeid.endswith("test_live_smoke_probe")

    verdict = _gate(repo)
    assert verdict.passed, f"smoke really ran and the gate still refused: {verdict.message}"


def test_the_attestation_carries_what_it_claims(tmp_path: Path) -> None:
    """A record that names neither the code nor the claim is decoration."""
    repo = _build_repo(tmp_path, PROBE_THAT_RUNS)
    _run_pytest(repo)

    run = _runs(repo)[0]

    assert run.commit_sha == _git(repo, "rev-parse", "HEAD"), (
        "the attestation must name the commit it exercised, or staleness is unknowable"
    )
    assert run.execution_kind == "live_smoke"
    assert run.acceptance_urn == ACCEPTANCE_URN, (
        "the run must be traceable back to the planner acceptance it discharges"
    )


# --------------------------------------------------------------------------- #
# Direction 2 — it did not run                                                 #
# --------------------------------------------------------------------------- #


def test_a_skipped_live_smoke_test_is_recorded_as_a_skip_and_closes_the_gate(
    tmp_path: Path,
) -> None:
    """#1076, closed: the skip is visible AND it does not satisfy the gate.

    Both halves matter. Recording nothing would also block the gate, but it
    would leave an operator unable to tell "smoke was skipped" from "smoke was
    never attempted" — which is precisely how C010-SMOKE-001 looked green.
    """
    repo = _build_repo(tmp_path, PROBE_THAT_SKIPS)

    result = _run_pytest(repo)
    assert result.returncode == 0, "a skipped test is not a suite failure"

    runs = _runs(repo)
    assert [r.outcome for r in runs] == ["skipped"], (
        f"the skip must be written down, loudly. stdout:\n{result.stdout}"
    )

    verdict = _gate(repo)
    assert not verdict.passed, "a skipped live-smoke test satisfied the smoke gate"
    assert "skipped" in verdict.message


def test_a_live_smoke_test_that_never_runs_leaves_no_attestation_and_closes_the_gate(
    tmp_path: Path,
) -> None:
    """Deselected, not executed, nothing recorded — and still blocked.

    The suite is green (it ran, and everything it selected passed), so this is
    the case a "did the tests pass?" gate waves through and an execution gate
    must not.
    """
    repo = _build_repo(tmp_path, PROBE_THAT_RUNS)

    result = _run_pytest(repo, "tests/test_unanchored.py")
    assert result.returncode == 0, f"the unanchored suite should pass:\n{result.stdout}"

    assert _runs(repo) == [], "a test that never ran must attest nothing"

    verdict = _gate(repo)
    assert not verdict.passed, (
        "a green pytest run that never executed the live-smoke test opened the gate"
    )
    assert "no smoke-execution attestation" in verdict.message


# --------------------------------------------------------------------------- #
# The ratchet — evidence about other code is not evidence about this code      #
# --------------------------------------------------------------------------- #


def test_an_attestation_goes_stale_when_the_code_moves_on(tmp_path: Path) -> None:
    """Smoke run at commit A must not license a transition at commit B."""
    repo = _build_repo(tmp_path, PROBE_THAT_RUNS)
    _run_pytest(repo)
    assert _gate(repo).passed, "precondition: the fresh attestation opens the gate"

    (repo / "tests" / "test_unanchored.py").write_text(
        PROBE_WITHOUT_ANCHOR + "\n\ndef test_added_later():\n    assert True\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "change the code after smoking it")

    verdict = _gate(repo)
    assert not verdict.passed, (
        "the gate accepted smoke evidence captured against different code"
    )
    assert "not at HEAD" in verdict.message
