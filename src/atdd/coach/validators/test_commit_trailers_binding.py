# URN: component:dispatch-validators:enforcement-substrate:test_commit_trailers_binding:backend:domain
# Runtime: python
# Purpose: Reverse-coherence binder for the coach.commit-trailers.* rule family (issue #517).

"""Validator binding for the ``coach.commit-trailers.*`` rule family.

The runtime tier-1 git watcher
(``src/atdd/coach/runtime/git_watcher.py``) emits a
``coach.commit-trailers.<trailer>-required`` violation when a commit
observed on a coach-watched worktree is missing a required trailer
(``Phase`` / ``WMBT-Urn`` / ``Agent-Id`` / ``Issue``). The runtime
emitter is the enforcer; this module exists so the substrate's
reverse-rule-coherence pass
(``coach.rule-id.validator-binding-violation`` →
``test_rule_validator_binding::test_every_enforced_rule_has_real_validator``)
can resolve the convention's ``validator:`` field to a real callable
that calls ``bind_rule(<id>)`` for each rule in the family.

Run:
    PYTHONPATH=src python3 -m pytest -q \\
        src/atdd/coach/validators/test_commit_trailers_binding.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.runtime.git_watcher import (
    REQUIRED_TRAILERS,
    GitWatcher,
)
from atdd.coach.utils.rule_binding import bind_rule


pytestmark = [pytest.mark.coach]


_PHASE_RULE = bind_rule("coach.commit-trailers.phase-required")
_WMBT_URN_RULE = bind_rule("coach.commit-trailers.wmbt-urn-required")
_AGENT_ID_RULE = bind_rule("coach.commit-trailers.agent-id-required")
_ISSUE_RULE = bind_rule("coach.commit-trailers.issue-required")


_RULE_FOR_TRAILER = {
    "Phase": _PHASE_RULE,
    "WMBT-Urn": _WMBT_URN_RULE,
    "Agent-Id": _AGENT_ID_RULE,
    "Issue": _ISSUE_RULE,
}


def _git(args, cwd: Path) -> str:
    import os
    import subprocess

    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "ATDD Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "ATDD Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    return subprocess.check_output(
        ["git", *args], cwd=str(cwd), text=True, env=env
    ).strip()


def _init_repo_with_trailerless_commit(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    _git(("init", "-q", "-b", "main"), cwd=repo)
    (repo / "seed.txt").write_text("seed\n")
    _git(("add", "seed.txt"), cwd=repo)
    _git(("commit", "-q", "-m", "seed"), cwd=repo)
    (repo / "f.txt").write_text("x\n")
    _git(("add", "f.txt"), cwd=repo)
    _git(("commit", "-q", "-m", "feat: bare\n\nbody only\n"), cwd=repo)
    return _git(("rev-parse", "HEAD"), cwd=repo)


def test_commit_trailers_rule_family_emits_each_required_trailer_id(tmp_path):
    """Reverse coherence for ``coach.commit-trailers.*``.

    Asserts the runtime watcher's emit path produces a violation under
    every rule in the family when a commit lacks every required
    trailer. This both anchors the convention's ``validator:`` field
    to this function (so the substrate's reverse-coherence pass
    resolves the binding) and guards against drift between
    ``REQUIRED_TRAILERS`` and the rule-id map.
    """
    repo = tmp_path / "wt"
    runtime_dir = tmp_path / "runtime"
    sha = _init_repo_with_trailerless_commit(repo)

    GitWatcher(
        agent_id="agent-binding",
        worktree=repo,
        runtime_dir=runtime_dir,
    ).observe(sha=sha)

    import json

    violations_path = runtime_dir / "validations" / sha / "violations.jsonl"
    raw = violations_path.read_text().splitlines()
    rule_ids = {json.loads(line)["rule_id"] for line in raw if line.strip()}

    expected_ids = {
        _RULE_FOR_TRAILER[trailer].rule_id for trailer in REQUIRED_TRAILERS
    }
    assert expected_ids <= rule_ids, (
        f"runtime watcher did not emit every coach.commit-trailers.* rule. "
        f"expected={sorted(expected_ids)} emitted={sorted(rule_ids)}"
    )
