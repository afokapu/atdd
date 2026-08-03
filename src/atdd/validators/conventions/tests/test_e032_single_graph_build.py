# URN: test:validate-conventions:tune-convention-suite:E032-GREEN-001-single-graph-build
# Acceptance: acc:validate-conventions:E032-RED-001-graph-rebuilt-per-evaluate
# Acceptance: acc:validate-conventions:E032-GREEN-001-graph-composed-once-per-session
# WMBT: wmbt:validate-conventions:E032
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E032 — the clean convention graph is composed ONCE per pytest session (#1414).

``load_composed_graph()`` walks ``plan/`` and every ``*.convention.yaml`` under
``src/atdd/``, costing ~2-3s. Every read-only baseline test evaluates its family
template against the same clean graph, so composing it per-test is pure waste.

E032-RED-001 (measured, not assumed): before the session fixture existed the 30
read-only baseline tests composed the graph **35** times, and the whole conventions
suite composed it **116** times — 328.1s of a 365.6s run.

E032-GREEN-001 asserts the MECHANISM, not a wall-clock budget: a timing assertion
would be cheapest to satisfy by deleting tests, which points straight at the
fault-injection coverage Y003 exists to protect, and CI wall-clock varies far too
much to gate on. Runtime is reported as a measured number, never asserted.

The read-only suite runs in a SUBPROCESS so the counter can monkeypatch the loader
without perturbing the session that is asserting on it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.validators.conventions._support.graph_loader import load_composed_graph

COUNTER_PLUGIN = "atdd.validators.conventions.tests.graph_build_counter"

# Read-only slice of the convention suite: every family's clean-baseline test. These
# assert their template flags nothing on the unmodified repo, so they can all share
# one composed graph. Fault-injection tests are deliberately excluded — they mutate
# the tree and MUST re-read it (see #1415).
READ_ONLY_SELECTOR = "baseline"

# The 13 families contributed 30 baseline tests when this gate was written. A lower
# count means the selector silently stopped matching and the gate went vacuous.
MIN_READ_ONLY_TESTS = 30


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def test_clean_graph_composed_once_across_readonly_suite(tmp_path: Path) -> None:
    root = _repo_root()
    count_file = tmp_path / "graph_builds.json"

    env = dict(os.environ)
    env["ATDD_GRAPH_BUILD_COUNT_FILE"] = str(count_file)

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            str(root / "src" / "atdd" / "validators" / "conventions"),
            "-k", READ_ONLY_SELECTOR,
            "-q", "-p", "no:cacheprovider", "-p", COUNTER_PLUGIN,
        ],
        cwd=root, env=env, capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, (
        f"read-only convention suite is not green:\n{result.stdout[-4000:]}"
    )
    assert count_file.exists(), f"counter plugin wrote no count:\n{result.stdout[-2000:]}"

    stats = json.loads(count_file.read_text(encoding="utf-8"))

    assert stats["selected"] >= MIN_READ_ONLY_TESTS, (
        f"vacuous gate: {READ_ONLY_SELECTOR!r} selected only {stats['selected']} tests, "
        f"expected >= {MIN_READ_ONLY_TESTS}"
    )
    assert stats["builds"] == 1, (
        f"the clean convention graph was composed {stats['builds']}x across "
        f"{stats['selected']} read-only tests; it must be composed exactly once "
        f"(session-scoped `clean_convention_graph` fixture)"
    )


def test_loader_is_not_memoized(tmp_path: Path) -> None:
    """E032-GREEN-001: the speedup is the session fixture, never a cache on the loader.

    ``load_composed_graph`` reads mutable files. Memoizing it would silently serve a
    stale graph to the fault-injection suites, which mutate the tree and re-read it to
    prove both that the fault is caught and that the revert left no residue.
    """
    assert not hasattr(load_composed_graph, "cache_info"), (
        "load_composed_graph is memoized (functools cache); fault-injection tests "
        "would be served a stale graph. Use the session-scoped fixture instead."
    )

    # Behavioural proof, not just introspection: a second call against the SAME root
    # must observe a mutation made between the two calls.
    plan = tmp_path / "plan" / "zztmp_e032"
    plan.mkdir(parents=True)
    (plan / "_zztmp_e032.yaml").write_text(
        'wagon: zztmp-e032\nurn: "wagon:zztmp-e032"\n', encoding="utf-8"
    )
    before = len(load_composed_graph(tmp_path).nodes())

    second = tmp_path / "plan" / "zztmp_e032_b"
    second.mkdir(parents=True)
    (second / "_zztmp_e032_b.yaml").write_text(
        'wagon: zztmp-e032-b\nurn: "wagon:zztmp-e032-b"\n', encoding="utf-8"
    )
    after = len(load_composed_graph(tmp_path).nodes())

    assert after == before + 1, (
        f"loader did not re-read the tree ({before} -> {after} nodes); it is caching"
    )
