# URN: test:govern-lifecycle:extract-workflow-wave-runner-and-atdd-resume-cli:E042-UNIT-004-atdd-resume-cli-command
# Acceptance: acc:govern-lifecycle:E042-UNIT-004-atdd-resume-cli-command
"""Unit test for E042-UNIT-004 (docs/coach-decomposition.md §3.4, §7.4, §13.9).

``atdd resume <run_id>`` is a new public CLI command: it is registered on the
top-level parser (and documents itself under ``--help``), builds the JSONL store +
runner for the repo, replays the run via ``JsonlTrainRunner.resume``, and errors
cleanly on an unknown run id.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from atdd.integrations.github import issue_state
from atdd.train import resume_cli
from atdd.train.persistence import JsonlPersistenceStore, load_conventions

from tests.coach._e040_helpers import build_temp_repo

ISSUE = 884
_SRC = Path(__file__).resolve().parents[2] / "src"


def _seed_run(tmp_path: Path) -> str:
    build_temp_repo(tmp_path, issue_number=ISSUE, status="GREEN")
    store = JsonlPersistenceStore(tmp_path)
    run_id = store.create_run(ISSUE, conventions=load_conventions(tmp_path))
    return str(run_id)


def test_resume_registered_and_documents_itself_under_help():
    """`atdd resume --help` renders via the top-level parser (real CLI surface)."""
    result = subprocess.run(
        [sys.executable, "-m", "atdd.cli", "resume", "--help"],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(_SRC), "CI": "true", "PATH": __import__("os").environ["PATH"]},
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "RUN_ID" in out
    assert "resume" in out.lower()


def test_resume_args_replays_existing_run(tmp_path, monkeypatch):
    # Hermetic: the default GitHub source resolves the live phase via issue_state;
    # stub it so materialize_evidence degrades to the manifest status (no network).
    monkeypatch.setattr(issue_state, "read_phase", lambda issue: None)
    run_id = _seed_run(tmp_path)

    rc = resume_cli.run_args(run_id=run_id, repo_root=tmp_path)

    assert rc == 0
    store = JsonlPersistenceStore(tmp_path)
    from atdd.train.types import RunId

    types = [e.type for e in store.replay_events(RunId(run_id))]
    assert "RunResumed" in types


def test_resume_args_unknown_run_returns_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(issue_state, "read_phase", lambda issue: None)
    build_temp_repo(tmp_path, issue_number=ISSUE, status="GREEN")

    rc = resume_cli.run_args(run_id="run-does-not-exist-00000000", repo_root=tmp_path)
    assert rc == 1


def test_resume_args_empty_run_dir_logs_keyerror_not_silent(tmp_path, monkeypatch, caplog):
    """A run dir with no event log must observably react (log), never silently swallow.

    Pins coder.logging.coach-silent-swallow: the ``store.load_run`` KeyError handler
    logs a WARNING (not a bare print/return) so the rule stays green.
    """
    import logging

    monkeypatch.setattr(issue_state, "read_phase", lambda issue: None)
    build_temp_repo(tmp_path, issue_number=ISSUE, status="GREEN")
    # A run dir that exists but holds no events → store.load_run raises KeyError.
    run_id = "run-884-20260531-deadbeef"
    (tmp_path / ".atdd" / "runtime" / "runs" / run_id).mkdir(parents=True)

    with caplog.at_level(logging.WARNING, logger="atdd.train.resume"):
        rc = resume_cli.run_args(run_id=run_id, repo_root=tmp_path)

    assert rc == 1
    assert any(
        r.levelno == logging.WARNING and "no event log" in r.getMessage()
        for r in caplog.records
    ), "the KeyError handler must log, not silently swallow"


def test_resume_run_help_exits_zero():
    """The standalone resume_cli.run argv wrapper also documents the command."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        resume_cli.run(["--help"])
    assert exc.value.code == 0
