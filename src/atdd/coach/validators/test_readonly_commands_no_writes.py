"""
Coach validator: read-only atdd commands must not mutate the working tree.

Issue: #342 — atdd <any-cmd> was silently rewriting `.atdd/config.yaml`
(`toolkit.last_version`) and writing `atdd.code-workspace` to the repo parent
directory on every invocation, including `atdd --help`. This validator gates
that regression: it spins up a fixture repo with a stale
`toolkit.last_version`, runs each read-only verb, and asserts that
`git status --porcelain` is empty after.

The fixture repo must satisfy two preconditions for the validator to be a
real signal:

1. `find_repo_root()` must locate it (so the CLI's bootstrap path actually
   reads the repo's `.atdd/config.yaml`).
2. `toolkit.last_version` must be older than the installed version (so the
   version-drift detector fires; otherwise the bug is masked).

Run via: `pytest src/atdd/coach/validators/test_readonly_commands_no_writes.py`
or as part of `atdd validate coach`.

Reference: src/atdd/coach/specs/cli-write-audit.md
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]


# Read-only verbs covered by GT-100/GT-200 in issue #342.
#
# Selection criteria:
#   - Does not require GitHub API access (so the validator can run offline).
#   - Does not require a populated plan/contracts/telemetry tree.
#   - Goes through `cli.cli()` -> `print_upgrade_sync_notice()` (i.e. exercises
#     the regression path).
#
# `validate` and `inventory` are intentionally omitted because they spawn a
# pytest subprocess / require a fully populated repo; the dispatcher unit test
# in tests/test_main_dispatcher.py covers the same regression path at unit
# resolution.
READONLY_COMMANDS: list[list[str]] = [
    ["--help"],
    ["version"],
    ["status"],
    ["gate"],
    ["gate", "--json"],
    ["urn", "families"],
    ["issue", "--help"],
    ["sync", "--status"],
]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a command in ``cwd`` capturing output."""
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={
            **os.environ,
            # Keep the PyPI freshness check from making network requests
            # during the validator. Disable upgrade banner side-channel
            # writes outside of repo too.
            "CI": "true",
            "ATDD_NO_UPDATE_CHECK": "1",
            "PYTHONPATH": str(REPO_ROOT / "src") + os.pathsep + os.environ.get(
                "PYTHONPATH", ""
            ),
        },
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return _run(["git", *args], cwd=cwd)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Build a minimal git repo with a stale-version `.atdd/config.yaml`.

    The stale `toolkit.last_version` ensures the version-drift bootstrap path
    fires; otherwise the bug is silent and the validator would always pass.
    """
    repo = tmp_path / "fixture"
    repo.mkdir()

    # Initialize git with a deterministic identity so commits succeed in CI.
    _git(repo, "init", "-q", "-b", "main").check_returncode()
    _git(repo, "config", "user.email", "validator@atdd.test").check_returncode()
    _git(repo, "config", "user.name", "ATDD Validator").check_returncode()
    _git(repo, "config", "commit.gpgsign", "false").check_returncode()

    atdd_dir = repo / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "config.yaml").write_text(
        textwrap.dedent(
            """\
            toolkit:
              last_version: 0.0.1
            sync:
              agents: []
            """
        )
    )

    # `atdd init` writes this entry in real consumer repos
    # (initializer.py:_ensure_gitignore_entry). Mirror it here so the
    # graph cache that some read-only verbs build (urn families, etc.)
    # does not show up as a git-status diff in the fixture. The cache
    # itself is not the regression under test.
    (repo / ".gitignore").write_text(".atdd/cache/\n")

    _git(repo, "add", "-A").check_returncode()
    _git(repo, "commit", "-q", "-m", "fixture").check_returncode()

    # Sanity: tree is clean before we run anything
    porcelain = _git(repo, "status", "--porcelain").stdout
    assert porcelain == "", f"Fixture not clean before test: {porcelain!r}"

    return repo


@pytest.mark.parametrize("verb", READONLY_COMMANDS, ids=lambda v: " ".join(v))
def test_readonly_command_leaves_tree_clean(
    fixture_repo: Path, verb: list[str]
) -> None:
    """A read-only atdd verb MUST NOT modify the working tree.

    Acceptance gate GT-100/GT-200 (issue #342): every command in
    READONLY_COMMANDS must satisfy
    ``git status --porcelain`` is empty after invocation, even when the
    repo's `.atdd/config.yaml` is at a stale `toolkit.last_version`.
    """
    cmd = [sys.executable, "-m", "atdd", *verb]
    result = _run(cmd, cwd=fixture_repo)

    # We don't assert on returncode here — `--help` exits 0, but other verbs
    # may have non-zero exits in the fixture (e.g. `urn families` when the
    # repo has no plan/). What matters is that the working tree is clean.
    porcelain = _git(fixture_repo, "status", "--porcelain").stdout

    # Files that may legitimately appear in a fixture run (e.g. an editor's
    # backup) should not — but we deliberately do NOT whitelist anything,
    # since the bug under test is exactly an unexpected write.
    assert porcelain == "", (
        f"`atdd {' '.join(verb)}` mutated the working tree.\n"
        f"git status --porcelain:\n{porcelain}\n"
        f"atdd stdout:\n{result.stdout}\n"
        f"atdd stderr:\n{result.stderr}"
    )

    # And no untracked files should have appeared in the parent (the
    # `atdd.code-workspace` regression target).
    parent_extras = sorted(
        p.name for p in fixture_repo.parent.iterdir() if p != fixture_repo
    )
    assert parent_extras == [], (
        f"`atdd {' '.join(verb)}` created files outside the repo: "
        f"{parent_extras!r}"
    )


def test_atdd_sync_upgrade_writes_last_version(fixture_repo: Path) -> None:
    """The explicit `atdd sync` verb is allowed (and required) to write.

    Acceptance gate GT-500: `atdd sync` is the canonical writer of
    `toolkit.last_version`. After running it, the value MUST be updated and
    the working tree MUST reflect that change (i.e. the write actually
    happened — the test would fail if `print_upgrade_sync_notice` were
    silently doing it earlier and `atdd sync` were a no-op).
    """
    config_path = fixture_repo / ".atdd" / "config.yaml"
    before = config_path.read_text()
    assert "0.0.1" in before, (
        "Precondition: fixture should start at toolkit.last_version: 0.0.1"
    )

    cmd = [sys.executable, "-m", "atdd", "sync"]
    proc = _run(cmd, cwd=fixture_repo)

    after = config_path.read_text()
    assert "0.0.1" not in after, (
        "atdd sync should bump toolkit.last_version off 0.0.1, but config "
        f"still contains it:\n{after}\n"
        f"--- subprocess stdout ---\n{proc.stdout}\n"
        f"--- subprocess stderr ---\n{proc.stderr}\n"
        f"--- returncode={proc.returncode} ---"
    )
