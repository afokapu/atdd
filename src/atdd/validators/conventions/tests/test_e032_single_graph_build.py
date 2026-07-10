# URN: test:validate-conventions:tune-convention-suite:E032-RED-001-single-graph-build
# Acceptance: acc:validate-conventions:E032-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E032
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E032 — the clean convention graph is composed ONCE per pytest session (#1414).

``load_composed_graph()`` walks ``plan/`` and every ``*.convention.yaml`` under
``src/atdd/``, costing ~2-3s. Every read-only baseline test evaluates its family
template against the same clean graph, so composing it per-test is pure waste: on
the pre-#1414 tree the 30 read-only baseline tests composed it 35 times.

This gate asserts the MECHANISM, not a wall-clock budget. A timing assertion would
be satisfiable by deleting tests — which points straight at the fault-injection
coverage Y003 exists to protect — and CI wall-clock varies far too much to gate on.

The read-only suite is run in a SUBPROCESS so the counter can monkeypatch the loader
without perturbing the session that is asserting on it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
