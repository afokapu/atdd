"""Fixture-based tests for ``atdd.integrations.github.checks`` (no live API)."""
from __future__ import annotations

import json

from atdd.integrations.github import _gh, checks

CHECK_RUNS_JSON = json.dumps({
    "check_runs": [
        {"name": "build", "conclusion": "success",
         "check_suite": {"id": 42}},
        {"name": "deploy", "conclusion": None},  # still running → PENDING
    ],
})


def test_read_check_runs_maps_conclusions_and_pending(monkeypatch):
    monkeypatch.setattr(
        _gh, "resolve_project_config",
        lambda repo_root=None: _gh.ProjectRef(repo="o/r", project_id="PVT_x"),
    )
    monkeypatch.setattr(_gh, "run_gh", lambda args, **kw: CHECK_RUNS_JSON)

    runs = checks.read_check_runs("abc123")
    by_name = {r.name: r for r in runs}
    assert by_name["build"].conclusion == "SUCCESS"
    assert by_name["build"].workflow_id == 42
    assert by_name["deploy"].conclusion == "PENDING"


def test_trigger_rerun_invokes_gh_run_rerun(monkeypatch):
    calls = []
    monkeypatch.setattr(_gh, "run_gh", lambda args, **kw: calls.append(list(args)) or "")

    checks.trigger_rerun(777)
    assert calls == [["run", "rerun", "777", "--failed"]]
