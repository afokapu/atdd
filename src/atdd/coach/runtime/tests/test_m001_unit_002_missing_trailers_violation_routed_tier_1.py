# URN: test:dispatch-validators:dispatch-tier-one-validators:M001-UNIT-002-missing-trailers-violation-routed-tier-1
# Acceptance: acc:dispatch-validators:M001-UNIT-002-missing-trailers-violation-routed-tier-1
# WMBT: wmbt:dispatch-validators:M001
# Phase: RED
# Layer: application
"""M001-UNIT-002 — missing trailers route a coach.commit-trailers.* violation.

Per spec §7.3, commit trailers are mechanically enforced at the producer side
by the pre-commit hook. The runtime tier-1 watcher mirrors that enforcement:
a commit observed without one of the required trailers (Phase, WMBT-Urn,
Agent-Id, Issue) produces a Violation under the coach.commit-trailers.* rule
family, conforming to validator-result.schema.json.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import atdd

pytestmark = [pytest.mark.platform]


ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
VALIDATOR_RESULT_SCHEMA = (
    ATDD_PKG_DIR / "coach" / "schemas" / "validator-result.schema.json"
)


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


def _validator_result_validator() -> Draft202012Validator:
    schema = json.loads(VALIDATOR_RESULT_SCHEMA.read_text())
    return Draft202012Validator(schema)


def _violations_for_sha(runtime_dir: Path, sha: str) -> list[dict]:
    path = runtime_dir / "validations" / sha / "violations.jsonl"
    if not path.exists():
        return []
    return _read_jsonl(path)


REQUIRED_TRAILERS = ["Phase", "WMBT-Urn", "Agent-Id", "Issue"]
RULE_NAMES = {
    "Phase": "coach.commit-trailers.phase-required",
    "WMBT-Urn": "coach.commit-trailers.wmbt-urn-required",
    "Agent-Id": "coach.commit-trailers.agent-id-required",
    "Issue": "coach.commit-trailers.issue-required",
}


def test_missing_phase_emits_phase_required_violation(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(
        worktree,
        "feat: missing phase\n\nWMBT-Urn: w\nAgent-Id: a\nIssue: 1\n",
    )

    GitWatcher(
        agent_id="agent-test", worktree=worktree, runtime_dir=runtime_dir
    ).observe(sha=sha)

    violations = _violations_for_sha(runtime_dir, sha)
    rule_ids = {v["rule_id"] for v in violations}
    assert RULE_NAMES["Phase"] in rule_ids


def test_missing_all_trailers_emits_full_family(tmp_path):
    """A commit with no trailers emits one violation per required trailer
    under the coach.commit-trailers.* family."""
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, "feat: missing every trailer\n\nbody only\n")

    GitWatcher(
        agent_id="agent-test", worktree=worktree, runtime_dir=runtime_dir
    ).observe(sha=sha)

    violations = _violations_for_sha(runtime_dir, sha)
    rule_ids = {v["rule_id"] for v in violations}
    for trailer, rule in RULE_NAMES.items():
        assert rule in rule_ids, f"expected {rule} for missing {trailer}"


def test_violations_conform_to_validator_result_schema(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, "feat: bad commit\n\nno trailers\n")

    GitWatcher(
        agent_id="agent-test", worktree=worktree, runtime_dir=runtime_dir
    ).observe(sha=sha)

    violations = _violations_for_sha(runtime_dir, sha)
    assert violations, "expected at least one violation for missing trailers"

    validator = _validator_result_validator()
    for v in violations:
        errors = list(validator.iter_errors(v))
        assert errors == [], (
            f"violation {v.get('rule_id')} failed schema: "
            f"{[e.message for e in errors]}"
        )


def test_violation_rule_ids_all_under_commit_trailers_family(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(worktree, "feat: nothing\n\n\n")

    GitWatcher(
        agent_id="agent-test", worktree=worktree, runtime_dir=runtime_dir
    ).observe(sha=sha)

    violations = _violations_for_sha(runtime_dir, sha)
    assert violations
    for v in violations:
        assert v["rule_id"].startswith("coach.commit-trailers."), v["rule_id"]


def test_well_formed_commit_emits_no_trailer_violations(tmp_path):
    from atdd.coach.runtime.git_watcher import GitWatcher

    worktree = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    _init_repo(worktree)
    sha = _commit(
        worktree,
        "feat: complete trailers\n"
        "\n"
        "Phase: RED\n"
        "WMBT-Urn: wmbt:dispatch-validators:M001\n"
        "Agent-Id: agent-test\n"
        "Issue: 517\n",
    )

    GitWatcher(
        agent_id="agent-test", worktree=worktree, runtime_dir=runtime_dir
    ).observe(sha=sha)

    violations = _violations_for_sha(runtime_dir, sha)
    assert violations == []
