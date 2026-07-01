# URN: test:govern-lifecycle:state:E059-SMOKE-001-publish-job-configures-git-identity-so-annotated-tag-creation-succeeds
# Acceptance: acc:govern-lifecycle:E059-SMOKE-001-publish-job-configures-git-identity-so-annotated-tag-creation-succeeds
# WMBT: wmbt:govern-lifecycle:E059
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E059-SMOKE-001 — publish.yml sets a git identity so `git tag -a` succeeds.

#1297. Publish run 28495533869 died at ``git tag -a v4.0.0`` with
``fatal: empty ident name`` because the ``tag-release`` job never configured a
git identity. This proves the fix end-to-end with the REAL git binary (no
mocks): (1) a real annotated ``git tag -a`` in a tmp repo with NO configured
identity fails with an empty-identity error, reproducing the run; (2) the same
tag succeeds once a release-bot identity is configured — so the fix is
necessary and sufficient; and (3) ``publish.yml`` configures both
``git config user.name`` and ``user.email`` in the ``tag-release`` job BEFORE the
drain step that runs the extension's tag/publish.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PUBLISH_YML = _REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _sanitized_env(home: Path) -> dict:
    """A git env with NO ambient identity (isolated HOME + no global/system config)."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    for k in (
        "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    ):
        env.pop(k, None)
    return env


@pytest.fixture()
def identity_less_repo(tmp_path):
    """A tmp repo with one commit but NO persistent git identity configured."""
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    env = _sanitized_env(home)
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    # Disable git's auto-guess-identity-from-OS-user so "no configured identity"
    # deterministically fails (as on the CI runner) rather than silently
    # succeeding on a dev box whose git can derive user@host.
    subprocess.run(["git", "config", "user.useConfigOnly", "true"],
                   cwd=repo, env=env, check=True)
    (repo / "f.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    # Give the commit an identity via per-command -c so NONE persists in config.
    subprocess.run(
        ["git", "-c", "user.name=seed", "-c", "user.email=seed@seed",
         "commit", "-q", "-m", "seed"],
        cwd=repo, env=env, check=True,
    )
    return repo, env


def test_annotated_tag_fails_without_identity_then_succeeds_with_one(identity_less_repo):
    repo, env = identity_less_repo

    # (1) Reproduce the run failure: annotated tag with no identity → empty ident.
    failed = subprocess.run(
        ["git", "tag", "-a", "v3.152.0", "-m", "Release v3.152.0"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert failed.returncode != 0
    assert "ident" in failed.stderr.lower()      # "empty ident name" / "unknown ... identity"

    # (2) The fix: configure a release-bot identity, then the same tag succeeds.
    subprocess.run(["git", "config", "user.name", "atdd-release-bot"],
                   cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "release-bot@atdd.local"],
                   cwd=repo, env=env, check=True)
    ok = subprocess.run(
        ["git", "tag", "-a", "v3.152.0", "-m", "Release v3.152.0"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert ok.returncode == 0, ok.stderr
    listed = subprocess.run(
        ["git", "tag", "--list", "v3.152.0"],
        cwd=repo, env=env, capture_output=True, text=True, check=True,
    )
    assert "v3.152.0" in listed.stdout.split()


def test_publish_yml_configures_git_identity_before_the_drain():
    text = _PUBLISH_YML.read_text()

    # Both identity fields are configured in the job.
    assert "git config user.name" in text
    assert "git config user.email" in text

    # And they are configured BEFORE the drain step that runs the extension
    # tag/publish (otherwise `git tag -a` in the drain would still fail). Anchor
    # on the drain STEP header (the `- name:` line), not the top-of-file comment
    # that also mentions the drain by name.
    idx_name = text.index("git config user.name")
    idx_drain_step = text.index("- name: Drain version_decided")
    assert idx_name < idx_drain_step, "git identity must be set before the drain step"
