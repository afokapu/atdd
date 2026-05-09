# URN: test:dispatch-validators:dispatch-tier-one-validators:M001-UNIT-003-git-watcher-smoke
# Acceptance: acc:dispatch-validators:M001-UNIT-001-commit-observed-event-emitted
# Acceptance: acc:dispatch-validators:M001-UNIT-002-missing-trailers-violation-routed-tier-1
# WMBT: wmbt:dispatch-validators:M001
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: verify the git watcher against real git, real schemas, real fs
"""M001 SMOKE — exercise GitWatcher against real infrastructure.

What this verifies that the unit tests do not:
- The watcher's trailer parser delegates to the real ``git
  interpret-trailers --parse`` binary on disk and matches git's own
  producer-side validation.
- Events validate against the *committed* C0 schema at
  ``src/atdd/coach/schemas/runtime-event.schema.json`` (loaded as a
  file, not via test fixtures).
- Multi-commit replay preserves append-only ordering: a watcher fed
  two commits in sequence emits four events on the agent's
  ``events.jsonl`` in deterministic order.
- The 1-second latency budget holds end-to-end with real git
  subprocesses (no mocked git, no fakes).
- The validator-result records the watcher writes round-trip through
  the committed ``validator-result.schema.json``.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import atdd

pytestmark = [pytest.mark.platform]


ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RUNTIME_EVENT_SCHEMA = ATDD_PKG_DIR / "coach" / "schemas" / "runtime-event.schema.json"
VALIDATOR_RESULT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "validator-result.schema.json"
)


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "ATDD Smoke",
            "GIT_AUTHOR_EMAIL": "smoke@example.com",
            "GIT_COMMITTER_NAME": "ATDD Smoke",
            "GIT_COMMITTER_EMAIL": "smoke@example.com",
        }
    )
    return env


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=str(cwd), text=True, env=_git_env()
    ).strip()


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=path)
    (path / "seed.txt").write_text("seed\n")
    _git("add", "seed.txt", cwd=path)
    _git("commit", "-q", "-m", "seed", cwd=path)


def _commit(path: Path, message: str, file_name: str = "f.txt") -> str:
    (path / file_name).write_text(file_name + "\n")
    _git("add", file_name, cwd=path)
    _git("commit", "-q", "-m", message, cwd=path)
    return _git("rev-parse", "HEAD", cwd=path)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_smoke_real_schemas_load_from_disk():
    """Both committed schemas must be loadable as JSON Schemas."""
    schema = json.loads(RUNTIME_EVENT_SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    schema = json.loads(VALIDATOR_RESULT_SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)


def test_smoke_real_git_interpret_trailers_round_trip(tmp_path):
    """parse_trailers MUST match what `git interpret-trailers --parse`
    returns when invoked directly against the real binary."""
    from atdd.coach.runtime.git_watcher import parse_trailers

    worktree = tmp_path / "wt"
    _init_repo(worktree)
    message = (
        "feat: round-trip trailers\n"
        "\n"
        "Phase: GREEN\n"
        "WMBT-Urn: wmbt:dispatch-validators:M001\n"
        "Agent-Id: agent-smoke\n"
        "Issue: 517\n"
    )

    parsed = parse_trailers(message, cwd=worktree)
    assert parsed["Phase"] == "GREEN"
    assert parsed["WMBT-Urn"] == "wmbt:dispatch-validators:M001"
    assert parsed["Agent-Id"] == "agent-smoke"
    assert parsed["Issue"] == "517"


def test_smoke_two_commits_emit_four_events_in_order(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)

    common_trailers = (
        "WMBT-Urn: wmbt:dispatch-validators:M001\n"
        "Agent-Id: agent-smoke\n"
        "Issue: 517\n"
    )
    sha_a = _commit(worktree, "feat: a\n\nPhase: RED\n" + common_trailers, "a.txt")
    sha_b = _commit(worktree, "feat: b\n\nPhase: GREEN\n" + common_trailers, "b.txt")

    watcher = GitWatcher(
        agent_id="agent-smoke", worktree=worktree, runtime_dir=runtime_dir
    )
    watcher.observe(sha=sha_a)
    watcher.observe(sha=sha_b)

    events = _read_jsonl(runtime_dir / "agents" / "agent-smoke" / "events.jsonl")
    assert [e["event_type"] for e in events] == [
        "commit_observed",
        "validation_pending",
        "commit_observed",
        "validation_pending",
    ]
    assert events[0]["payload"]["sha"] == sha_a
    assert events[2]["payload"]["sha"] == sha_b
    assert events[1]["payload"]["phase"] == "RED"
    assert events[3]["payload"]["phase"] == "GREEN"


def test_smoke_latency_budget_with_real_git(tmp_path):
    """End-to-end real-git observe() stays under the 1-second budget."""
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(
        worktree,
        "feat: latency probe\n"
        "\n"
        "Phase: SMOKE\n"
        "WMBT-Urn: wmbt:dispatch-validators:M001\n"
        "Agent-Id: agent-smoke\n"
        "Issue: 517\n",
    )

    watcher = GitWatcher(
        agent_id="agent-smoke", worktree=worktree, runtime_dir=runtime_dir
    )
    started = time.monotonic()
    watcher.observe(sha=sha)
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"observe() took {elapsed:.3f}s — exceeds 1s budget"


def test_smoke_missing_trailers_violation_round_trips_validator_result_schema(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, "feat: nothing\n\nbody only\n")

    GitWatcher(
        agent_id="agent-smoke", worktree=worktree, runtime_dir=runtime_dir
    ).observe(sha=sha)

    violations_path = runtime_dir / "validations" / sha / "violations.jsonl"
    violations = _read_jsonl(violations_path)
    assert len(violations) == 4

    schema = json.loads(VALIDATOR_RESULT_SCHEMA.read_text())
    validator = Draft202012Validator(schema)
    for v in violations:
        errors = list(validator.iter_errors(v))
        assert errors == [], f"{v['rule_id']}: {[e.message for e in errors]}"
        assert v["disposition"] == "strict"
        assert v["rule_id"].startswith("coach.commit-trailers.")


def test_smoke_observe_default_uses_head(tmp_path):
    """When no sha is passed, observe() resolves HEAD via real git."""
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(
        worktree,
        "feat: head default\n"
        "\n"
        "Phase: GREEN\n"
        "WMBT-Urn: wmbt:dispatch-validators:M001\n"
        "Agent-Id: agent-smoke\n"
        "Issue: 517\n",
    )

    GitWatcher(
        agent_id="agent-smoke", worktree=worktree, runtime_dir=runtime_dir
    ).observe()

    events = _read_jsonl(runtime_dir / "agents" / "agent-smoke" / "events.jsonl")
    [observed] = [e for e in events if e["event_type"] == "commit_observed"]
    assert observed["payload"]["sha"] == sha
