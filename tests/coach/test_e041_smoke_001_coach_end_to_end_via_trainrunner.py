# URN: test:govern-lifecycle:extract-workflow-issue-runner-and-workflow-runner-protocol:E041-SMOKE-001-coach-end-to-end-via-trainrunner
# Acceptance: acc:govern-lifecycle:E041-SMOKE-001-coach-end-to-end-via-trainrunner
"""SMOKE test for E041-SMOKE-001 (docs/coach-decomposition.md §6.1, §13.8, §3.3).

A real ``atdd coach <N>`` invocation drives one issue through the TrainRunner seam
against a real temp repo (a real ``runs/<run_id>/`` scaffold lands on disk), a repo
grep confirms no ``coach.commands.coach._drive_*`` private call remains outside the
deprecated shim, and the new train modules stay within the §3.3 dependency rules.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import atdd
from atdd.coach.commands import coach
from atdd.train import issue_runner as issue_runner_mod

from tests.coach._e040_helpers import build_temp_repo

pytestmark = [pytest.mark.platform]

_SRC = Path(atdd.__file__).resolve().parent


def test_coach_run_drives_via_trainrunner_and_writes_real_run(tmp_path, monkeypatch):
    build_temp_repo(tmp_path, issue_number=895, status="INIT")
    monkeypatch.chdir(tmp_path)
    # #1486: the observer was decommissioned and train.wave_runner now defaults its
    # _observer_factory seam to a no-op, so the old
    # `monkeypatch.setattr(observer_mod, "MultiAgentObserver", _NullObserver)` stub is
    # no longer needed. The TrainRunner path under test is unchanged.
    monkeypatch.setattr(coach, "_read_current_github_phase", lambda n: None)

    drove: list[int] = []

    def _fake_drive(cfg, sm, runtime_dir, **kwargs):
        drove.append(sm.issue_number)
        return 0

    monkeypatch.setattr(issue_runner_mod, "drive_single_issue", _fake_drive)

    rc = coach.run([895])
    assert rc == 0
    assert drove == [895], "issue must be driven once via the runner"

    runs_dir = tmp_path / ".atdd" / "runtime" / "runs"
    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()] if runs_dir.is_dir() else []
    assert run_dirs, "JsonlTrainRunner.start_issue must write a durable runs/<run_id>/ dir"
    events_text = (run_dirs[0] / "events.jsonl").read_text()
    assert "RunStarted" in events_text


def test_no_private_drive_calls_remain_outside_the_shim():
    """grep src/ for coach.commands.coach._drive_* — only coach.py (the shim) may match."""
    pattern = re.compile(r"coach\._drive_|coach\.commands\.coach\._drive_")
    offenders: list[str] = []
    shim_file = _SRC / "coach" / "commands" / "coach.py"
    for py in _SRC.rglob("*.py"):
        if py == shim_file:
            continue  # the deprecated shim definitions live here by design
        if "/tests/" in str(py) or py.name.startswith("test_"):
            continue
        for i, line in enumerate(py.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{py.relative_to(_SRC)}:{i}: {line.strip()}")
    assert not offenders, "private drive calls outside the shim:\n" + "\n".join(offenders)


def test_train_runner_modules_obey_section_3_3():
    import ast

    forbidden = ("atdd.cli", "atdd.observer")
    for rel in ("train/runner_iface.py", "train/issue_runner.py", "train/runners/jsonl.py"):
        src = _SRC / rel
        tree = ast.parse(src.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for fb in forbidden:
            assert not any(
                imp == fb or imp.startswith(fb + ".") for imp in imported
            ), f"{rel} imports forbidden {fb!r}"
