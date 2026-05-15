# URN: test:observe-and-correct:observer-runtime-and-rules:OBSSCAN-001-scan-excludes-own-runtime
# Acceptance: acc:observe-and-correct:OBSSCAN-001-runtime-excluded
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: integration
"""Regression tests for #706 — `Observer._scan_worktree` must exclude the
observer's own runtime output.

The observer writes `corrections.jsonl` / `cli-return.jsonl` into
`<runtime_dir>/agents/<id>/`, which lives inside the scanned worktree. Before
#706 `_scan_worktree` had no exclusions, so every correction-write was detected
as a change, fired `out-of-scope-edit`, wrote another correction — an unbounded
self-feedback loop (observed: 694/694 self-referential corrections on a single
coach 690 dispatch).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands import observer

pytestmark = [pytest.mark.platform]


def _observer(worktree: Path, runtime_dir: Path) -> observer.Observer:
    return observer.Observer(
        agent_id="planner-999-abc-observer",
        runtime_dir=runtime_dir,
        rules_dir=None,
        worktree=worktree,
    )


def test_scan_excludes_observer_runtime_output(tmp_path: Path):
    """A file written under runtime_dir does NOT surface as a worktree
    change — this is the loop-breaking fix."""
    worktree = tmp_path / "wt"
    (worktree / "src").mkdir(parents=True)
    runtime_dir = worktree / ".atdd" / "runtime"
    (runtime_dir / "agents" / "planner-999-abc-observer").mkdir(parents=True)

    obs = _observer(worktree, runtime_dir)

    # Baseline scan.
    assert obs._scan_worktree() == []

    # The observer writes a correction into its own runtime dir ...
    (runtime_dir / "agents" / "planner-999-abc-observer" / "corrections.jsonl").write_text(
        '{"rule_id": "x"}\n', encoding="utf-8"
    )
    # ... and the persona touches a real source file.
    (worktree / "src" / "feature.py").write_text("x = 1\n", encoding="utf-8")

    changed = obs._scan_worktree()

    assert "src/feature.py" in changed, "a real source change must be detected"
    assert not any(".atdd/runtime" in c for c in changed), (
        f"observer runtime output must NOT be scanned (#706 loop): {changed}"
    )


def test_scan_excludes_git_and_pycache(tmp_path: Path):
    worktree = tmp_path / "wt"
    (worktree / "src").mkdir(parents=True)
    (worktree / ".git").mkdir()
    (worktree / "src" / "__pycache__").mkdir()
    runtime_dir = worktree / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)

    obs = _observer(worktree, runtime_dir)
    assert obs._scan_worktree() == []

    (worktree / ".git" / "index").write_text("gitstuff\n", encoding="utf-8")
    (worktree / "src" / "__pycache__" / "m.pyc").write_text("bytecode\n", encoding="utf-8")
    (worktree / "src" / "real.py").write_text("y = 2\n", encoding="utf-8")

    changed = obs._scan_worktree()
    assert "src/real.py" in changed
    assert not any(".git" in c for c in changed)
    assert not any("__pycache__" in c for c in changed)


def test_scan_does_not_over_prune(tmp_path: Path):
    """The exclusion must not swallow legitimate .atdd/ edits outside
    runtime/ — e.g. plan/ files or .atdd/manifest.yaml."""
    worktree = tmp_path / "wt"
    (worktree / "plan").mkdir(parents=True)
    (worktree / ".atdd").mkdir()
    runtime_dir = worktree / ".atdd" / "runtime"
    runtime_dir.mkdir(parents=True)

    obs = _observer(worktree, runtime_dir)
    assert obs._scan_worktree() == []

    (worktree / "plan" / "wagon.yaml").write_text("a: 1\n", encoding="utf-8")
    (worktree / ".atdd" / "manifest.yaml").write_text("m: 1\n", encoding="utf-8")

    changed = obs._scan_worktree()
    assert "plan/wagon.yaml" in changed
    assert ".atdd/manifest.yaml" in changed, (
        "edits to .atdd/ OUTSIDE runtime/ must still be observed"
    )
