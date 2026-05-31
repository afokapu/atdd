# URN: test:govern-lifecycle:extract-workflow-issue-runner-and-workflow-runner-protocol:E041-UNIT-003-cli-routes-via-trainrunner-and-reserved-flags
# Acceptance: acc:govern-lifecycle:E041-UNIT-003-cli-routes-via-trainrunner-and-reserved-flags
"""Unit test for E041-UNIT-003 (docs/coach-decomposition.md §7.4, §13.8).

``atdd coach <N>`` instantiates ``JsonlTrainRunner`` + ``PolicyHandle`` and drives
through ``start_issue``; ``--runner`` defaults to ``jsonl`` and reserves
``temporal`` / ``langgraph`` as ``NotImplementedError``; the ``train.runner``
config key is recognized.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands import coach
from atdd.train.runner_iface import PolicyHandle
from atdd.train.runners.jsonl import JsonlTrainRunner

from tests.coach._e040_helpers import build_temp_repo


def test_runner_flag_parses_and_defaults_to_jsonl():
    cfg = coach.parse_cli(["895"])
    assert cfg.runner == "jsonl"
    cfg2 = coach.parse_cli(["895", "--runner", "jsonl"])
    assert cfg2.runner == "jsonl"
    for name in ("temporal", "langgraph"):
        assert coach.parse_cli(["895", "--runner", name]).runner == name


@pytest.mark.parametrize("name", ["temporal", "langgraph"])
def test_reserved_runners_raise_notimplemented_pointing_to_doc(name):
    with pytest.raises(NotImplementedError) as exc:
        coach._require_supported_runner(name)
    msg = str(exc.value)
    assert "7.2" in msg or "7.3" in msg
    assert "coach-decomposition" in msg


def test_jsonl_runner_resolves_without_error():
    # No exception for the supported runner.
    coach._require_supported_runner("jsonl")


def test_cold_start_constructs_jsonl_train_runner_and_policy(tmp_path, monkeypatch):
    """run() must instantiate a JsonlTrainRunner + PolicyHandle for the cold-start."""
    captured: dict = {}

    def _capture(cfg, machines, runtime_dir, *, runner=None, policy=None, **kwargs):
        captured["runner"] = runner
        captured["policy"] = policy
        return coach.ColdStartResult(rc=0, blocked=[])

    monkeypatch.setattr(coach, "_execute_cold_start", _capture)
    # Keep the run hermetic — no GitHub label reads during machine setup.
    monkeypatch.setattr(coach, "_read_current_github_phase", lambda n: None)

    rc = coach.run([895], _runtime_dir_override=tmp_path)
    assert rc == 0
    assert isinstance(captured["runner"], JsonlTrainRunner)
    assert isinstance(captured["policy"], PolicyHandle)


def test_execute_cold_start_reaches_drive_via_runner_not_private_call(tmp_path, monkeypatch):
    """With a runner injected, _execute_cold_start drives via runner.start_issue."""
    build_temp_repo(tmp_path, issue_number=895, status="INIT")

    started: list[int] = []

    class _FakeRunner:
        def bind_state_machines(self, machines):
            self._machines = machines

        def bind_drive_context(self, **kwargs):
            self._ctx = kwargs

        def start_issue(self, issue_number, *, policy):
            started.append(issue_number)
            return f"run-{issue_number}"

        def rc_for(self, run_id):
            return 0

    # The private drive shim must NOT be called when a runner is present.
    sentinel = {"called": False}

    def _boom(*a, **k):
        sentinel["called"] = True
        return 0

    monkeypatch.setattr(coach, "_drive_single_issue", _boom)

    cfg = coach.Config(issue_numbers=[895])
    machines = [coach.initialize_state_machine(895)]
    policy = object()
    coach._execute_cold_start(
        cfg, machines, tmp_path / ".atdd" / "runtime",
        runner=_FakeRunner(), policy=policy,
        _observer_factory=_NullObserver,
    )

    assert started == [895]
    assert sentinel["called"] is False


class _NullObserver:
    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def stop(self):
        pass


def test_get_train_runner_config_defaults_to_jsonl(tmp_path):
    from atdd.coach.utils.config import get_train_runner_config

    # No config file → default.
    assert get_train_runner_config(tmp_path)["runner"] == "jsonl"
