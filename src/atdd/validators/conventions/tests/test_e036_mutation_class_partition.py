# URN: test:validate-conventions:tune-convention-suite:E036-mutation-class-partition
# Acceptance: acc:validate-conventions:E036-RED-001-unmarked-writer-runs-in-the-parallel-subset
# Acceptance: acc:validate-conventions:E036-GREEN-001-guard-fails-the-unmarked-writer
# WMBT: wmbt:validate-conventions:E036
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E036 — the mutation-class partition that makes ``-n auto`` safe (#1418, folding in #1417).

The convention suite runs as two CI subsets: everything NOT marked
``convention_filesystem_mutation`` under ``pytest-xdist -n auto``, and the marked remainder
serially. xdist workers share ONE checkout, so the whole safety argument rests on the marker
being complete — a single unmarked writer in the parallel subset corrupts its siblings.

Nothing about that is self-enforcing, so both halves are exercised here against a synthetic,
hermetic pytest suite rooted in ``tmp_path`` (its own ``pytest.ini`` makes it the rootdir, so
the guard's notion of "the checkout" is the temp dir, not this repo):

  E036-RED-001  the hazard. With the markers declared but no guard, an unmarked test that
                writes inside the checkout is SELECTED by ``-m "not convention_filesystem_mutation"``
                and passes green while writing — exactly the test that would corrupt the
                parallel workers, and nothing notices.

  E036-GREEN-001  the mechanism. With the guard armed, that same test FAILS and names the path
                it wrote; so does a test whose SUBPROCESS writes the checkout and reverts (the
                shape a fault test's ``finally`` leaves — invisible to ``git status``, caught by
                an mtime fingerprint); and so does a serial test that takes the session graph.
                Meanwhile the four cases that are NOT hazards — a marked writer, a write outside
                the checkout, a plain reader, and a subprocess that reads the checkout without
                writing it — all stay green. That last one is the load-bearing case: after #1458
                the nested ``pytest`` runs in E032/E033/E035 write nothing, and calling every
                spawner serial would drag all of them into the serial job for no reason.

Runtime is reported on the PR as a measured number, never asserted: CI wall-clock swings far
more than the effect, and the cheapest way to satisfy a timing gate is to delete the fault
coverage this suite exists to protect.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# The three mutation classes, declared for the synthetic rootdir exactly as pyproject declares
# them for the real one.
_PYTEST_INI = """\
[pytest]
markers =
    convention_readonly: read-only
    convention_inmemory_fault: clone-and-mutate, writes nothing
    convention_filesystem_mutation: writes the checkout — serial only
"""

# The guard, wired the way conventions/conftest.py wires it. `clean_convention_graph` is a
# stand-in for the real session graph — the guard only cares that the fixture was requested.
_GUARDED_CONFTEST = """\
from pathlib import Path

import pytest

from atdd.validators.conventions._support.mutation_guard import (  # noqa: F401
    assign_default_class,
    mutation_class_guard,
)

_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items):
    assign_default_class(items, _DIR)


@pytest.fixture(scope="session")
def clean_convention_graph():
    return object()
"""

# The pre-guard world: the markers exist, so the CI split would already deselect a *marked*
# test — but nothing checks that the marker is actually on the writers.
_UNGUARDED_CONFTEST = """\
import pytest


@pytest.fixture(scope="session")
def clean_convention_graph():
    return object()
"""

_PROBE_SUITE = """\
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def test_unmarked_writer_inside_checkout():
    (HERE / "victim.txt").write_text("mutated", encoding="utf-8")


@pytest.mark.convention_filesystem_mutation
def test_marked_writer_inside_checkout():
    (HERE / "declared.txt").write_text("mutated", encoding="utf-8")


def test_unmarked_writer_outside_checkout(tmp_path):
    (tmp_path / "elsewhere.txt").write_text("not a hazard", encoding="utf-8")


def test_unmarked_reader():
    assert (HERE / "pytest.ini").read_text(encoding="utf-8")


@pytest.mark.convention_filesystem_mutation
def test_marked_test_taking_the_session_graph(clean_convention_graph):
    assert clean_convention_graph is not None


def test_unmarked_subprocess_writing_the_checkout():
    # Writes a file and deletes it again — the shape a fault test's `finally` leaves behind.
    # `git status` sees a clean tree afterwards; the tree was still dirty in between, which is
    # the window that corrupts a parallel worker. Only an mtime fingerprint catches it.
    code = (
        "import pathlib;"
        f"p = pathlib.Path(r'{HERE}') / 'probe.tmp';"
        "p.write_text('x'); p.unlink()"
    )
    subprocess.run([sys.executable, "-c", code], cwd=str(HERE), check=True)


def test_unmarked_subprocess_reading_the_checkout():
    # Spawns a subprocess over the checkout but writes NOTHING. This is NOT a hazard, and it is
    # the case that matters: after #1458 the nested `pytest` runs in E032/E033/E035 write nothing,
    # and one of them is literally the test asserting so. A guard that called every spawner serial
    # would drag all of them into the serial job — and did, until it was fixed.
    subprocess.run([sys.executable, "-c", "pass"], cwd=str(HERE), check=True)
"""

# The unmarked hazards the guard must catch, and the safe cases it must NOT flag.
_HAZARDS = ("test_unmarked_writer_inside_checkout", "test_unmarked_subprocess_writing_the_checkout")
_SESSION_GRAPH_ABUSE = "test_marked_test_taking_the_session_graph"
_MUST_STAY_GREEN = (
    "test_marked_writer_inside_checkout",
    "test_unmarked_writer_outside_checkout",
    "test_unmarked_reader",
    "test_unmarked_subprocess_reading_the_checkout",
)

_PARALLEL_SUBSET = ["-m", "not convention_filesystem_mutation"]


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _synthetic_suite(tmp_path: Path, conftest: str) -> Path:
    """A throwaway pytest rootdir. Its own pytest.ini makes tmp_path the rootdir, which is
    what the guard reads as "the checkout" — so the probe's writes land inside it."""
    (tmp_path / "pytest.ini").write_text(_PYTEST_INI, encoding="utf-8")
    (tmp_path / "conftest.py").write_text(conftest, encoding="utf-8")
    (tmp_path / "test_probe.py").write_text(_PROBE_SUITE, encoding="utf-8")
    return tmp_path


def _run(suite: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_repo_root() / "src"))
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(suite), "-p", "no:cacheprovider", "-v", *args],
        cwd=suite, env=env, capture_output=True, text=True, timeout=300,
    )


def _outcome(stdout: str, test_name: str) -> str:
    """PASSED / FAILED / ERROR / NOT-SELECTED for one test, off `-v` output.

    The guard fires in fixture TEARDOWN, and pytest reports that as an `ERROR` in the short
    summary while the per-test `-v` line still reads `PASSED` — the call phase did pass. So a
    verdict is the WORST outcome across every line naming the test, not the first one seen.
    Reading only the `-v` line would score a caught hazard as green, which is the one mistake
    this test cannot afford to make.
    """
    verdicts = set()
    for line in stdout.splitlines():
        if f"::{test_name}" not in line:
            continue
        head = line.strip().split(" ", 1)[0]
        if head in ("ERROR", "FAILED"):
            verdicts.add(head)
        else:
            verdicts.update(v for v in ("PASSED", "FAILED", "ERROR") if v in line)
    for worst in ("ERROR", "FAILED", "PASSED"):
        if worst in verdicts:
            return worst
    return "NOT-SELECTED"


def test_red_unmarked_writer_runs_in_the_parallel_subset(tmp_path: Path) -> None:
    """E036-RED-001: without the guard, the writer is selected into the `-n auto` subset and
    passes green while mutating the shared checkout. Nothing stands between it and the
    parallel workers — this is the hazard the marker alone cannot close."""
    suite = _synthetic_suite(tmp_path, _UNGUARDED_CONFTEST)

    result = _run(suite, *_PARALLEL_SUBSET)

    assert _outcome(result.stdout, _HAZARDS[0]) == "PASSED", (
        "the unmarked writer was not selected-and-green in the parallel subset, so the RED "
        f"characterization is vacuous:\n{result.stdout[-3000:]}"
    )
    assert (suite / "victim.txt").exists(), (
        "the unmarked writer did not actually write the checkout — the probe is not probing"
    )
    # ...and the marked one is correctly held back, so the deselection itself works. The gap is
    # only ever the completeness of the marker.
    assert _outcome(result.stdout, "test_marked_writer_inside_checkout") == "NOT-SELECTED"


def test_green_guard_fails_the_unmarked_writer_and_the_marked_graph_consumer(tmp_path: Path) -> None:
    """E036-GREEN-001: with the guard armed, every hazard is red and every non-hazard is green."""
    suite = _synthetic_suite(tmp_path, _GUARDED_CONFTEST)

    result = _run(suite)  # the whole synthetic suite, both classes

    for hazard in _HAZARDS:
        assert _outcome(result.stdout, hazard) in ("FAILED", "ERROR"), (
            f"the guard let `{hazard}` through — an unmarked test that touches the checkout "
            f"would run under -n auto against its siblings:\n{result.stdout[-3000:]}"
        )
    assert "convention_filesystem_mutation" in result.stdout, (
        "the guard's failure message does not name the marker the author has to add"
    )
    assert "victim.txt" in result.stdout, (
        "the guard's failure message does not name the path that was written"
    )

    assert _outcome(result.stdout, _SESSION_GRAPH_ABUSE) in ("FAILED", "ERROR"), (
        "a serial test was handed `clean_convention_graph` — the session graph is composed "
        "before the mutation, so the test's assertions about its own injection are vacuous:\n"
        f"{result.stdout[-3000:]}"
    )

    for safe in _MUST_STAY_GREEN:
        assert _outcome(result.stdout, safe) == "PASSED", (
            f"the guard flagged `{safe}`, which is not a hazard — a marked writer and a write "
            f"outside the checkout are both fine, and a false positive here would push tests "
            f"into the serial subset for no reason:\n{result.stdout[-3000:]}"
        )
