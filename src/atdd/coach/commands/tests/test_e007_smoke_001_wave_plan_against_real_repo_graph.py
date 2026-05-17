# URN: test:integration-hardening:coach-graph-aware-orchestration:E007-SMOKE-001-wave-plan-against-real-repo-graph
# Acceptance: acc:integration-hardening:E007-SMOKE-001-wave-plan-against-real-repo-graph
# WMBT: wmbt:integration-hardening:E007
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Smoke: true
"""E007-SMOKE-001 — wave ordering is derived from the real ``atdd repo graph``
substrate.

This SMOKE test scaffolds a real git repo with a real plan/ tree and proves —
against real infrastructure, with NO substituted collaborators — that the
wagon consume graph the coach relies on for wave ordering is read from real
files and the real ``atdd`` CLI:

  1. ``atdd repo graph --format json`` exits 0 as a subprocess against the
     real repo and emits non-empty stdout.
  2. The real ``coach.runtime.graph.wagon_deps`` helper, run against the real
     scaffolded plan/ directory, returns the real consume edge
     ``wagon-b -> wagon-a`` — so a downstream-wagon issue would be ordered
     strictly after its upstream.

No mocking, no monkeypatch, no stubbed graph data: the helper reads the same
plan files ``atdd repo graph`` reads.

Opt-in: real-infrastructure SMOKE tests are gated behind ATDD_RUN_SMOKE=1 so
CI stays fast and hermetic. Run locally with:

    ATDD_RUN_SMOKE=1 pytest <this file> -v

RED expectation (when opted in): ``coach.runtime.graph`` does not exist yet →
the second test fails on import.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.platform,
    pytest.mark.skipif(
        os.environ.get("ATDD_RUN_SMOKE") != "1",
        reason="real-infrastructure SMOKE test — set ATDD_RUN_SMOKE=1 to run",
    ),
]

# parents[4] from tests/ → commands/ → coach/ → atdd/ → src/
_SRC_ROOT = Path(__file__).resolve().parents[4]


def _scaffold_real_repo(tmp_path: Path) -> None:
    """A real git repo with two wagons where wagon-b consumes from wagon-a."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    plan = tmp_path / "plan"
    (plan / "wagon_a").mkdir(parents=True)
    (plan / "wagon_a" / "_wagon_a.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-a
            urn: "wagon:wagon-a"
            name: "Upstream Wagon"
            description: "Produces a contract consumed downstream."
            theme: commons
            features: []
            produce:
              - name: commons:test:upstream-contract
                to: external
            consume: []
        """)
    )
    (plan / "wagon_b").mkdir(parents=True)
    (plan / "wagon_b" / "_wagon_b.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-b
            urn: "wagon:wagon-b"
            name: "Downstream Wagon"
            description: "Consumes the upstream contract."
            theme: commons
            features: []
            produce: []
            consume:
              - name: commons:test:upstream-contract
                from: wagon:wagon-a
        """)
    )
    (plan / "_trains.yaml").write_text(
        textwrap.dedent("""\
            trains:
              0-commons:
                00-nominal:
                  - train_id: "0002-test-train"
                    title: "Test Train"
                    path: "plan/_trains/0002-test-train.yaml"
                    wagons:
                      - wagon-a
                      - wagon-b
        """)
    )


def test_real_repo_graph_subprocess_exits_zero(tmp_path: Path) -> None:
    _scaffold_real_repo(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(_SRC_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "repo", "graph", "--format", "json"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"atdd repo graph failed: {proc.stderr}"
    assert proc.stdout.strip(), "atdd repo graph emitted empty stdout"


def test_wagon_deps_reads_real_consume_edge(tmp_path: Path) -> None:
    _scaffold_real_repo(tmp_path)

    # Real helper, real plan files — no substitution. The cwd is the real repo
    # so wagon_deps reads the same plan/ tree atdd repo graph reads.
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        from atdd.coach.runtime.graph import wagon_deps

        deps = wagon_deps("wagon-b")
    finally:
        os.chdir(cwd)

    assert deps == ["wagon-a"], (
        f"downstream wagon-b must depend on upstream wagon-a per the real "
        f"consume graph, got {deps}"
    )
