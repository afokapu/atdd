# URN: component:govern-lifecycle:enforcement-substrate:test_git_hook_env_scrub:backend:domain
# Runtime: python
# Purpose: The validator runner must scrub git-hook-injected env vars so validator
#          subprocesses see the repo-at-cwd git context, not the push operation's (#932).
"""
Tests for ``_scrub_git_hook_env`` (issue #932).

When ``atdd validate`` runs from a git hook (pre-push / pre-commit), git has
exported ``GIT_DIR`` / ``GIT_INDEX_FILE`` / ``GIT_WORK_TREE`` / … into the
environment. If those leak into the validator subprocess, every validator
that shells out to ``git`` (commit-trailer checks, "leaves tree clean"
readonly checks, core.bare baseline, manifest-write discipline) sees the
WRONG git context and fails deterministically on state unrelated to the diff
— so a standalone ``atdd validate`` is green while the same gate run from the
pre-push hook blocks every push.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.test_runner import _GIT_HOOK_ENV_VARS, _scrub_git_hook_env

pytestmark = [pytest.mark.platform]


def test_scrub_removes_git_hook_vars():
    env = {
        "GIT_DIR": "/repo/.git",
        "GIT_INDEX_FILE": "/repo/.git/index",
        "GIT_WORK_TREE": "/repo",
        "GIT_PREFIX": "",
        "PATH": "/usr/bin",
        "ATDD_REPO_ROOT": "/repo",
    }
    scrubbed = _scrub_git_hook_env(dict(env))
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX"):
        assert var not in scrubbed, f"{var} should be scrubbed"
    # Non-git env is preserved.
    assert scrubbed["PATH"] == "/usr/bin"
    assert scrubbed["ATDD_REPO_ROOT"] == "/repo"


def test_scrub_is_noop_without_git_vars():
    env = {"PATH": "/usr/bin", "HOME": "/home/me"}
    assert _scrub_git_hook_env(dict(env)) == env


def test_all_known_git_hook_vars_are_scrubbed():
    env = {var: "x" for var in _GIT_HOOK_ENV_VARS}
    env["KEEP"] = "1"
    scrubbed = _scrub_git_hook_env(dict(env))
    assert scrubbed == {"KEEP": "1"}
