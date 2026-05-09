# URN: test:dispatch-validators:dispatch-tier-one-validators:M001-UNIT-001-commit-observed-event-emitted
# Acceptance: acc:dispatch-validators:M001-UNIT-001-commit-observed-event-emitted
# WMBT: wmbt:dispatch-validators:M001
# Phase: RED
# Layer: application
"""M001-UNIT-001 — commit_observed event with parsed trailers + validation_pending.

Per spec §6.4 step 1+2: when an agent commits on a coach-watched worktree,
the runtime tier-1 dispatch must observe the commit, parse the conventional
trailers (Phase, WMBT-Urn, Agent-Id, Issue) from `git log -1 --format=%B <sha>`,
and emit a `commit_observed` event plus a downstream `validation_pending` event
keyed by the trailer-resolved (phase, scope).

Both events conform to runtime-event.schema.json (frozen at C0 by #483).
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import atdd

pytestmark = [pytest.mark.platform]


ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=str(cwd), text=True, env=_git_env()
    ).strip()


def _git_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "ATDD Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "ATDD Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    return env


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=path)
    (path / "seed.txt").write_text("seed\n")
    _git("add", "seed.txt", cwd=path)
    _git("commit", "-q", "-m", "seed", cwd=path)


def _commit(path: Path, message: str, file_name: str = "f.txt") -> str:
    (path / file_name).write_text("x\n", encoding="utf-8")
    _git("add", file_name, cwd=path)
    _git("commit", "-q", "-m", message, cwd=path)
    return _git("rev-parse", "HEAD", cwd=path)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _runtime_event_validator() -> Draft202012Validator:
    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())
    return Draft202012Validator(schema)


def _good_message() -> str:
    return (
        "feat(coach): exercise commit_observed emission\n"
        "\n"
        "Phase: GREEN\n"
        "WMBT-Urn: wmbt:dispatch-validators:M001\n"
        "Agent-Id: agent-M1-coach-git-watcher\n"
        "Issue: 517\n"
    )


def test_commit_observed_event_emitted_with_payload(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    parent = _git("rev-parse", "HEAD", cwd=worktree)
    sha = _commit(worktree, _good_message())

    watcher = GitWatcher(
        agent_id="agent-test",
        worktree=worktree,
        runtime_dir=runtime_dir,
    )
    watcher.observe(sha=sha)

    events_path = runtime_dir / "agents" / "agent-test" / "events.jsonl"
    assert events_path.exists()
    events = _read_jsonl(events_path)

    [observed] = [e for e in events if e["event_type"] == "commit_observed"]
    payload = observed["payload"]
    assert payload["worktree"] == str(worktree)
    assert payload["sha"] == sha
    assert payload["parent_sha"] == parent


def test_commit_observed_event_carries_parsed_trailers(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, _good_message())

    watcher = GitWatcher(
        agent_id="agent-test",
        worktree=worktree,
        runtime_dir=runtime_dir,
    )
    watcher.observe(sha=sha)

    events_path = runtime_dir / "agents" / "agent-test" / "events.jsonl"
    [observed] = [
        e for e in _read_jsonl(events_path) if e["event_type"] == "commit_observed"
    ]
    trailers = observed["payload"]["trailers"]
    assert trailers["Phase"] == "GREEN"
    assert trailers["WMBT-Urn"] == "wmbt:dispatch-validators:M001"
    assert trailers["Agent-Id"] == "agent-M1-coach-git-watcher"
    assert trailers["Issue"] == "517"


def test_validation_pending_event_emitted_keyed_by_phase_and_scope(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, _good_message())

    watcher = GitWatcher(
        agent_id="agent-test",
        worktree=worktree,
        runtime_dir=runtime_dir,
    )
    watcher.observe(sha=sha)

    events_path = runtime_dir / "agents" / "agent-test" / "events.jsonl"
    events = _read_jsonl(events_path)
    [pending] = [e for e in events if e["event_type"] == "validation_pending"]

    payload = pending["payload"]
    assert payload["phase"] == "GREEN"
    assert payload["sha"] == sha
    scope = payload["scope"]
    assert scope["wmbt_urn"] == "wmbt:dispatch-validators:M001"
    assert scope["issue"] == "517"
    assert scope["agent_id"] == "agent-M1-coach-git-watcher"


def test_both_events_validate_against_runtime_event_schema(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, _good_message())

    watcher = GitWatcher(
        agent_id="agent-test",
        worktree=worktree,
        runtime_dir=runtime_dir,
    )
    watcher.observe(sha=sha)

    events_path = runtime_dir / "agents" / "agent-test" / "events.jsonl"
    events = _read_jsonl(events_path)
    validator = _runtime_event_validator()
    for event in events:
        errors = list(validator.iter_errors(event))
        assert errors == [], (
            f"event {event.get('event_type')} failed schema: "
            f"{[e.message for e in errors]}"
        )


def test_validation_pending_emitted_after_commit_observed(tmp_path):
    """Ordering invariant: commit_observed must appear in events.jsonl
    before validation_pending so #M3's selection resolver only acts on
    commits coach has already seen."""
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, _good_message())

    watcher = GitWatcher(
        agent_id="agent-test",
        worktree=worktree,
        runtime_dir=runtime_dir,
    )
    watcher.observe(sha=sha)

    events_path = runtime_dir / "agents" / "agent-test" / "events.jsonl"
    events = _read_jsonl(events_path)
    types_in_order = [e["event_type"] for e in events]
    co_idx = types_in_order.index("commit_observed")
    vp_idx = types_in_order.index("validation_pending")
    assert co_idx < vp_idx


def test_observe_latency_within_one_second(tmp_path):
    """Spec §6.4: from HEAD advance to commit_observed event emission ≤ 1s."""
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, _good_message())

    watcher = GitWatcher(
        agent_id="agent-test",
        worktree=worktree,
        runtime_dir=runtime_dir,
    )

    started = time.monotonic()
    watcher.observe(sha=sha)
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"observe() took {elapsed:.3f}s, exceeds 1s budget"
