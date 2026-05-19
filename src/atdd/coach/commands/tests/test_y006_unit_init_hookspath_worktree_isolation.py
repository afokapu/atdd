# Acceptance: acc:integration-hardening:Y006-UNIT-001-install-hooks-uses-worktree-scope-in-linked-worktree
# Acceptance: acc:integration-hardening:Y006-UNIT-002-install-hooks-uses-shared-scope-in-main-worktree
# Acceptance: acc:integration-hardening:Y006-UNIT-003-worktree-config-extension-enabled-before-worktree-write
"""Unit tests for Y006: atdd init --force must use --worktree for core.hooksPath in linked worktrees.

Background: Before this fix, _install_hooks called 'git config core.hooksPath <abs>'
without --worktree, writing to the shared .git/config and contaminating all sibling
worktrees (Wave 12 contamination class, same as core.bare/#619/#629/#771).

The fix detects whether CWD is a linked worktree (git rev-parse --git-common-dir != --git-dir),
enables extensions.worktreeConfig idempotently, and writes via 'git config --worktree'.

Test hygiene: all subprocess calls use monkeypatching; no real git writes happen.
See test_y006_smoke_init_hookspath_worktree_isolation.py for the real-repo smoke test.
"""
from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.platform]


class _FakeCompletedProcess:
    """Minimal subprocess.CompletedProcess stub."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_initializer(tmp_path: Path) -> ProjectInitializer:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    return ProjectInitializer(target_dir=tmp_path)


def _capture_git_config_calls(calls: List) -> None:
    """Filter captured subprocess.run calls to only git-config ones."""
    return [
        c for c in calls
        if c[0][0] == ["git", "config"] or (
            isinstance(c[0][0], list) and len(c[0][0]) >= 2
            and c[0][0][0] == "git" and c[0][0][1] == "config"
        )
    ]


def _build_run_side_effect(linked: bool, worktree_config_enabled: bool = True):
    """Return a side_effect callable that simulates subprocess.run for hook tests.

    When linked=True the stub answers worktree-detection queries as a linked worktree.
    """

    def _side_effect(cmd, **kwargs):
        if isinstance(cmd, list):
            if "rev-parse" in cmd:
                if "--git-common-dir" in cmd:
                    # In a linked worktree, common-dir differs from git-dir
                    return _FakeCompletedProcess(stdout="/repo/.git\n" if linked else "/repo/.git\n")
                if "--git-dir" in cmd:
                    # In a linked worktree, git-dir points to worktrees/<name>
                    return _FakeCompletedProcess(
                        stdout="/repo/.git/worktrees/feat-x\n" if linked else "/repo/.git\n"
                    )
            if "config" in cmd and "--get" in cmd and "extensions.worktreeConfig" in cmd:
                return _FakeCompletedProcess(
                    returncode=0 if worktree_config_enabled else 1,
                    stdout="true\n" if worktree_config_enabled else "",
                )
        return _FakeCompletedProcess()

    return _side_effect


class TestY006Unit001LinkedWorktreeUsesWorktreeFlag:
    """Y006-UNIT-001: _install_hooks uses --worktree flag in a linked worktree."""

    def test_git_config_call_includes_worktree_flag(self, tmp_path: Path) -> None:
        """When CWD is a linked worktree, git config call must include '--worktree'."""
        ini = _make_initializer(tmp_path)
        captured: List = []

        def _capturing_run(cmd, **kwargs):
            captured.append(cmd)
            return _build_run_side_effect(linked=True)(cmd, **kwargs)

        # Create a fake template file so the hook copy loop runs
        tmpl_dir = tmp_path / "templates" / "hooks"
        tmpl_dir.mkdir(parents=True)
        (tmpl_dir / "pre-commit").write_text("#!/bin/sh\n")

        with (
            patch.object(ini, "package_root", tmp_path),
            patch("subprocess.run", side_effect=_capturing_run),
        ):
            ini._install_hooks(force=True)

        git_config_cmds = [c for c in captured if isinstance(c, list) and "config" in c]
        hookspath_writes = [c for c in git_config_cmds if "core.hooksPath" in c]

        assert hookspath_writes, (
            f"_install_hooks must call 'git config ... core.hooksPath' at least once; "
            f"captured: {captured}"
        )
        assert any("--worktree" in c for c in hookspath_writes), (
            f"In a linked worktree, git config for core.hooksPath must use '--worktree'; "
            f"got hookspath writes: {hookspath_writes}"
        )

    def test_no_bare_git_config_in_linked_worktree(self, tmp_path: Path) -> None:
        """When CWD is a linked worktree, unscoped 'git config core.hooksPath' must NOT appear."""
        ini = _make_initializer(tmp_path)
        captured: List = []

        def _capturing_run(cmd, **kwargs):
            captured.append(cmd)
            return _build_run_side_effect(linked=True)(cmd, **kwargs)

        tmpl_dir = tmp_path / "templates" / "hooks"
        tmpl_dir.mkdir(parents=True)
        (tmpl_dir / "pre-commit").write_text("#!/bin/sh\n")

        with (
            patch.object(ini, "package_root", tmp_path),
            patch("subprocess.run", side_effect=_capturing_run),
        ):
            ini._install_hooks(force=True)

        # An unscoped write would look like: ["git", "config", "core.hooksPath", ...]
        # A scoped write would look like: ["git", "config", "--worktree", "core.hooksPath", ...]
        unscoped_writes = [
            c for c in captured
            if isinstance(c, list)
            and len(c) >= 3
            and c[:2] == ["git", "config"]
            and "core.hooksPath" in c
            and "--worktree" not in c
        ]
        assert not unscoped_writes, (
            f"In a linked worktree, NO unscoped 'git config core.hooksPath' must appear; "
            f"found: {unscoped_writes}"
        )


class TestY006Unit002MainWorktreeUsesSharedScope:
    """Y006-UNIT-002: _install_hooks keeps the unscoped form in the main worktree."""

    def test_git_config_call_has_no_worktree_flag_in_main(self, tmp_path: Path) -> None:
        """When CWD is the main worktree, git config for core.hooksPath must NOT use '--worktree'."""
        ini = _make_initializer(tmp_path)
        captured: List = []

        def _capturing_run(cmd, **kwargs):
            captured.append(cmd)
            return _build_run_side_effect(linked=False)(cmd, **kwargs)

        tmpl_dir = tmp_path / "templates" / "hooks"
        tmpl_dir.mkdir(parents=True)
        (tmpl_dir / "pre-commit").write_text("#!/bin/sh\n")

        with (
            patch.object(ini, "package_root", tmp_path),
            patch("subprocess.run", side_effect=_capturing_run),
        ):
            ini._install_hooks(force=True)

        hookspath_writes = [
            c for c in captured
            if isinstance(c, list) and "core.hooksPath" in c
        ]
        assert hookspath_writes, (
            "_install_hooks must call git config core.hooksPath at least once"
        )
        assert all("--worktree" not in c for c in hookspath_writes), (
            f"In the main worktree, '--worktree' must NOT be used for core.hooksPath; "
            f"got: {hookspath_writes}"
        )


class TestY006Unit003WorktreeConfigEnabledBeforeWrite:
    """Y006-UNIT-003: extensions.worktreeConfig is enabled before --worktree write."""

    def test_extensions_worktree_config_enabled_when_absent(self, tmp_path: Path) -> None:
        """If extensions.worktreeConfig is not set, _install_hooks enables it first."""
        ini = _make_initializer(tmp_path)
        captured: List = []

        def _capturing_run(cmd, **kwargs):
            captured.append(cmd)
            return _build_run_side_effect(linked=True, worktree_config_enabled=False)(cmd, **kwargs)

        tmpl_dir = tmp_path / "templates" / "hooks"
        tmpl_dir.mkdir(parents=True)
        (tmpl_dir / "pre-commit").write_text("#!/bin/sh\n")

        with (
            patch.object(ini, "package_root", tmp_path),
            patch("subprocess.run", side_effect=_capturing_run),
        ):
            ini._install_hooks(force=True)

        # Find the index of the extensions.worktreeConfig enable call
        ext_enable = [
            i for i, c in enumerate(captured)
            if isinstance(c, list) and "extensions.worktreeConfig" in c and "true" in c
        ]
        hookspath_writes = [
            i for i, c in enumerate(captured)
            if isinstance(c, list) and "core.hooksPath" in c
        ]

        assert ext_enable, (
            "When extensions.worktreeConfig is absent, _install_hooks must enable it; "
            f"captured: {captured}"
        )
        assert hookspath_writes, (
            "_install_hooks must write core.hooksPath; captured: {captured}"
        )
        assert min(ext_enable) < min(hookspath_writes), (
            "extensions.worktreeConfig must be enabled BEFORE the core.hooksPath write; "
            f"enable indices: {ext_enable}, hooksPath indices: {hookspath_writes}"
        )

    def test_extensions_worktree_config_not_duplicated_when_already_set(self, tmp_path: Path) -> None:
        """If extensions.worktreeConfig is already true, it is NOT set again."""
        ini = _make_initializer(tmp_path)
        captured: List = []

        def _capturing_run(cmd, **kwargs):
            captured.append(cmd)
            return _build_run_side_effect(linked=True, worktree_config_enabled=True)(cmd, **kwargs)

        tmpl_dir = tmp_path / "templates" / "hooks"
        tmpl_dir.mkdir(parents=True)
        (tmpl_dir / "pre-commit").write_text("#!/bin/sh\n")

        with (
            patch.object(ini, "package_root", tmp_path),
            patch("subprocess.run", side_effect=_capturing_run),
        ):
            ini._install_hooks(force=True)

        ext_set_calls = [
            c for c in captured
            if isinstance(c, list)
            and "config" in c
            and "extensions.worktreeConfig" in c
            and "true" in c
            and "--get" not in c
        ]
        assert not ext_set_calls, (
            "When extensions.worktreeConfig is already true, it must NOT be set again; "
            f"found: {ext_set_calls}"
        )
