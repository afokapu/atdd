"""The live-smoke harness for the #1602 smoke-execution chain.

This module is the *harness* an ``execution_kind: live_smoke`` acceptance is
allowed to lean on: it drives the whole attestation chain against real
infrastructure and returns evidence **computed from what actually happened**.
Nothing here reports a fixed shape — every value in
:func:`smoke_execution_chain`'s result is read back out of a real process, a
real git repository, a real SQLite State Store, or the real gate's verdict. That
is the difference the ``live-smoke-evidence-must-not-be-constant`` rule (E060)
exists to police, and this harness is the repo's first subject for it.

WHAT "REAL INFRASTRUCTURE" IS FOR A LIFECYCLE TOOLKIT. There is no HTTP service
to point at; the live surface of this feature is:

* the real ``git`` binary, building a real repository with real history;
* the real ``pytest`` binary, in a real subprocess, over that repository;
* the real ``pytest11`` **entry-point** discovery path, driven from packaging
  metadata equivalent to what ``pip install atdd`` leaves behind — the only way a
  consumer's pytest ever reaches the attestation hook;
* the real State Store (SQLite on disk), written by that run and read back here;
* the real :class:`~atdd.coach.gate.smoke_execution_check.SmokeExecutionGateCheck`.

None of it is stubbed. The harness is deliberately incapable of manufacturing an
attestation itself: it can only run pytest and then look.

WHY THE PROBE REPO IS A FIXTURE AND NOT THIS REPO. The chain's negative
direction — "no run, no attestation, gate CLOSED" — cannot be exercised against
a live repository whose store already carries evidence, and rewinding a real
store to prove a negative would be a fabrication. So the harness builds a
throwaway repository per invocation and exercises both directions inside it. The
code under test is this working tree's ``src`` in every case; only the *subject*
repository is synthetic.

INSTALLED-PACKAGE CAVEAT. :func:`declared_pytest11_entry_points` reads this
repo's ``pyproject.toml``, so the harness runs from a source checkout, not from
an installed wheel. That is the point: it asserts against the declaration that
makes the hook reachable, rather than restating it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

#: The issue whose gate this chain exercises, and the work item the fixture
#: repository's store is keyed by. Both live inside the probe repo — nothing here
#: reads or writes the developer's real store (see :func:`_control_root`).
ISSUE = 1602
SLUG = "smoke-gate-probe"
BRANCH = f"feat/{SLUG}"
ACCEPTANCE_URN = "acc:smoke-gate-probe:live-smoke-executes"

#: ``src/`` of this working tree — the code the subprocess must import, so the
#: run exercises the change under test rather than an installed wheel.
#: ``live_smoke.py`` sits at ``src/atdd/coach/gate/``, hence four parents up.
SRC_ROOT = Path(__file__).resolve().parents[3]

#: The declaration the whole activation path hangs off. Read, never assumed.
PYPROJECT = SRC_ROOT.parent / "pyproject.toml"

#: The dist name pytest's autoload machinery will see — the real one, because the
#: point of the exercise is to be indistinguishable from ``pip install atdd``.
#: Harmless when atdd really is installed in the runner's environment: pluggy
#: skips an entry point whose *name* is already registered, and both copies name
#: the same module, which ``PYTHONPATH`` resolves to this working tree either way.
DIST_NAME = "atdd"

_CONTROL_ROOT_ENV = "ATDD_CONTROL_ROOT"
_REPO_ROOT_ENV = "ATDD_REPO_ROOT"
_GIT_TIMEOUT_S = 60
_PYTEST_TIMEOUT_S = 300

_PROBE_HEADER = f"""\
# Acceptance: {ACCEPTANCE_URN}
\"\"\"The live-smoke probe the fixture acceptance is anchored to.\"\"\"
import time
"""

#: A probe that executes and passes — the chain's *positive* direction, and the
#: negative control for the gate: a gate that refuses everything would satisfy
#: every other row here and be worthless.
PROBE_THAT_RUNS = _PROBE_HEADER + """

def test_live_smoke_probe():
    time.sleep(0.05)  # a measurable duration: a 0s "run" is the #1192 tell
    assert True
"""

#: A probe that never executes despite a green suite — the #1076 failure mode.
#: Held as source text rather than as a real decorator so this module is not
#: itself scanned as a self-skipping live-smoke test.
PROBE_THAT_DOES_NOT_EXECUTE = _PROBE_HEADER + """
import pytest


@pytest.mark.skip(reason="the #1076 failure mode: passing by never executing")
def test_live_smoke_probe():
    time.sleep(0.05)
    assert True
"""

#: A test bound to no acceptance — proves the hook attests the anchored test and
#: nothing else.
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
def git(repo: Path, *args: str) -> str:
    """Run git in *repo* with a pinned identity, returning stripped stdout.

    Raises on a non-zero exit: a harness that shrugged off a failed ``git
    commit`` would go on to attest against a repository that does not exist in
    the shape it claims.
    """
    proc = subprocess.run(
        ["git", "-c", "user.email=probe@atdd.test", "-c", "user.name=probe", *args],
        cwd=str(repo), capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {proc.stderr}")
    return proc.stdout.strip()


def build_probe_repo(root: Path, probe_source: str) -> Path:
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

    git(repo, "init", "-q", "-b", BRANCH)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "probe repo")

    from atdd.state.evidence import open_state_store

    with _control_root(repo):
        with open_state_store(control_root=repo) as store:
            store.objects.upsert(SLUG, "work_item", state="SMOKE")
            store.external_refs.link(SLUG, "github", "issue", str(ISSUE))
    return repo


def declared_pytest11_entry_points() -> Dict[str, str]:
    """``{name: target}`` from ``[project.entry-points.pytest11]`` in pyproject.

    The single source of truth for how a consumer's pytest finds the substrate
    plugin. Read rather than restated so the harness cannot drift away from the
    thing it claims to be replicating.
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - Python 3.10
        import tomli as tomllib  # type: ignore[import-not-found]

    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    return dict(data["project"]["entry-points"]["pytest11"])


def installed_metadata(parent: Path) -> Path:
    """Materialize the ``.dist-info`` ``pip install atdd`` would have left behind.

    Returns a directory to put on the subprocess's ``PYTHONPATH``. Nothing here
    is a stand-in for the mechanism under test: pytest still enumerates
    distributions with ``importlib.metadata``, still resolves the ``pytest11``
    group, still imports the module the entry point names, and still calls its
    ``pytest_configure``. The only thing supplied is the packaging metadata an
    uninstalled tree does not have — copied out of ``pyproject.toml``, so it says
    exactly what a real install would say and nothing more.

    This exists because entry points are read from *installed distribution
    metadata*, never from ``sys.path``/``PYTHONPATH``. A subprocess given only
    ``PYTHONPATH`` imports ``atdd`` fine and never loads the plugin — the run is
    green and records nothing. Handing pytest ``-p atdd.tester.substrate.plugin``
    would paper over that while proving nothing about a real consumer.
    """
    meta_root = parent / "installed-metadata"
    dist_info = meta_root / f"{DIST_NAME}-0.0.0.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    dist_info.joinpath("METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {DIST_NAME}\nVersion: 0.0.0\n"
    )
    dist_info.joinpath("entry_points.txt").write_text(
        "[pytest11]\n"
        + "".join(f"{name} = {target}\n" for name, target in sorted(
            declared_pytest11_entry_points().items()
        ))
    )
    return meta_root


def run_probe_pytest(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run pytest over the fixture repo in a subprocess, importing OUR source.

    The subprocess is given two path entries and no plugin flags: the working
    tree's ``src`` (so the code under test is the code that runs) and the
    synthesized dist metadata (so the plugin is auto-loaded the way a consumer's
    installed atdd is auto-loaded).

    ``ATDD_CONTROL_ROOT``/``ATDD_REPO_ROOT`` pin both resolvers at the fixture
    repo, so the run can neither read nor write the developer's real store.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (str(installed_metadata(repo.parent)), str(SRC_ROOT))
    )
    env[_CONTROL_ROOT_ENV] = str(repo)
    env[_REPO_ROOT_ENV] = str(repo)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra],
        cwd=str(repo), capture_output=True, text=True, timeout=_PYTEST_TIMEOUT_S,
        env=env,
    )


# --------------------------------------------------------------------------- #
# Reading the chain's output back                                              #
# --------------------------------------------------------------------------- #
@contextmanager
def _control_root(repo: Path) -> Iterator[None]:
    """Pin in-process store resolution at *repo* for the duration of the block.

    The Control Root resolver honours ``ATDD_CONTROL_ROOT`` above everything
    else, and this harness is invoked from a pytest run whose own environment may
    point at a real project. Setting it per-call rather than leaving it to a test
    fixture makes the harness structurally unable to touch a store it did not
    create — the strongest form of "this proves nothing about your real data".
    """
    previous = os.environ.get(_CONTROL_ROOT_ENV)
    os.environ[_CONTROL_ROOT_ENV] = str(repo)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_CONTROL_ROOT_ENV, None)
        else:
            os.environ[_CONTROL_ROOT_ENV] = previous


def attested_runs(repo: Path) -> List[Any]:
    """Every :class:`~atdd.state.evidence.SmokeRun` the probe repo's store holds."""
    from atdd.state.evidence import open_state_store, smoke_executions

    with _control_root(repo):
        with open_state_store(control_root=repo) as store:
            return smoke_executions(store, SLUG)


def gate_verdict(repo: Path) -> Any:
    """The real ``SMOKE->REFACTOR`` verdict for the probe repo's work item."""
    from atdd.coach.gate.decision import GateContext
    from atdd.coach.gate.smoke_execution_check import SmokeExecutionGateCheck

    with _control_root(repo):
        return SmokeExecutionGateCheck().run(GateContext(
            issue_number=ISSUE, from_phase="SMOKE", to_phase="REFACTOR", worktree=repo,
        ))


# --------------------------------------------------------------------------- #
# The harness proper                                                           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChainEvidence:
    """What the live chain actually did — every field measured, none assumed.

    Held as a dataclass rather than returned loose so a caller cannot silently
    assert against a key that was never produced.
    """

    pytest_returncode: int
    gate_open_before_run: bool
    attested_run_count: int
    attested_outcome: Optional[str]
    attested_duration_s: float
    attested_commit_sha: Optional[str]
    attested_execution_kind: Optional[str]
    attested_acceptance_urn: Optional[str]
    attested_nodeid: Optional[str]
    head_sha: str
    gate_open_after_run: bool
    gate_message_after_run: str
    unexecuted_outcomes: List[str]
    gate_open_without_execution: bool
    gate_message_without_execution: str


def smoke_execution_chain(workdir: Path) -> ChainEvidence:
    """Drive the #1602 chain end-to-end, both directions, and report what happened.

    Two independent fixture repositories, because the two directions are two
    different worlds and reusing one would let the first run's evidence leak into
    the second's verdict:

    * ``executed/`` — the probe runs and passes. Read the store, ask the gate.
    * ``unexecuted/`` — the probe is collected but never executes, the suite is
      still green. Read the store, ask the gate.

    Every returned field is measured after the fact: the subprocess's exit code,
    the rows the pytest hook wrote, git's own HEAD, and the gate's verdict object.
    Nothing is asserted here — judging is the caller's job, and a harness that
    decided for its caller could not be used to observe a failure.
    """
    workdir = Path(workdir)

    executed = build_probe_repo(workdir / "executed", PROBE_THAT_RUNS)
    before = gate_verdict(executed)
    result = run_probe_pytest(executed)
    runs = attested_runs(executed)
    after = gate_verdict(executed)
    run = runs[0] if runs else None

    unexecuted = build_probe_repo(workdir / "unexecuted", PROBE_THAT_DOES_NOT_EXECUTE)
    run_probe_pytest(unexecuted)
    unexecuted_runs = attested_runs(unexecuted)
    unexecuted_verdict = gate_verdict(unexecuted)

    return ChainEvidence(
        pytest_returncode=result.returncode,
        gate_open_before_run=bool(before.passed),
        attested_run_count=len(runs),
        attested_outcome=getattr(run, "outcome", None),
        attested_duration_s=float(getattr(run, "duration_s", 0.0) or 0.0),
        attested_commit_sha=getattr(run, "commit_sha", None),
        attested_execution_kind=getattr(run, "execution_kind", None),
        attested_acceptance_urn=getattr(run, "acceptance_urn", None),
        attested_nodeid=getattr(run, "nodeid", None),
        head_sha=git(executed, "rev-parse", "HEAD"),
        gate_open_after_run=bool(after.passed),
        gate_message_after_run=str(after.message),
        unexecuted_outcomes=[r.outcome for r in unexecuted_runs],
        gate_open_without_execution=bool(unexecuted_verdict.passed),
        gate_message_without_execution=str(unexecuted_verdict.message),
    )


__all__ = [
    "ACCEPTANCE_URN",
    "BRANCH",
    "ChainEvidence",
    "DIST_NAME",
    "ISSUE",
    "PROBE_THAT_DOES_NOT_EXECUTE",
    "PROBE_THAT_RUNS",
    "PROBE_WITHOUT_ANCHOR",
    "PYPROJECT",
    "SLUG",
    "SRC_ROOT",
    "WMBT_YAML",
    "attested_runs",
    "build_probe_repo",
    "declared_pytest11_entry_points",
    "gate_verdict",
    "git",
    "installed_metadata",
    "run_probe_pytest",
    "smoke_execution_chain",
]
