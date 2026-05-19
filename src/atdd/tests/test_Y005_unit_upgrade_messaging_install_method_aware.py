# Acceptance: acc:integration-hardening:Y005-UNIT-001-detect-install-method-pipx
# Acceptance: acc:integration-hardening:Y005-UNIT-002-detect-install-method-editable
# Acceptance: acc:integration-hardening:Y005-UNIT-003-detect-install-method-pip
# Acceptance: acc:integration-hardening:Y005-UNIT-004-upgrade-command-pipx
# Acceptance: acc:integration-hardening:Y005-UNIT-005-upgrade-command-pip
# Acceptance: acc:integration-hardening:Y005-UNIT-006-upgrade-command-editable
# Acceptance: acc:integration-hardening:Y005-UNIT-007-no-hardcoded-pip-in-user-messages
# Acceptance: acc:integration-hardening:Y005-UNIT-008-check-for-updates-uses-upgrade-command
# Acceptance: acc:integration-hardening:Y005-UNIT-009-upgrader-uses-upgrade-command
"""Unit tests for install-method-aware upgrade messaging (issue #782).

detect_install_method() classifies the running atdd install as pipx, editable,
pip, or unknown. upgrade_command() returns the correct upgrade command string.
All user-facing upgrade messages use upgrade_command() rather than hardcoding
'pip install --upgrade atdd'.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.version_check import (
    check_for_updates,
    detect_install_method,
    upgrade_command,
)


# ---------------------------------------------------------------------------
# Y005-UNIT-001: detect_install_method() returns 'pipx' for pipx paths
# ---------------------------------------------------------------------------
class TestDetectInstallMethodPipx:
    def test_pipx_venvs_path(self):
        pipx_python = "/home/user/.local/pipx/venvs/atdd/bin/python"
        with patch("sys.executable", pipx_python):
            assert detect_install_method() == "pipx"

    def test_pipx_shared_libs_path(self):
        pipx_python = "/home/user/.local/share/pipx/venvs/atdd/bin/python3"
        with patch("sys.executable", pipx_python):
            assert detect_install_method() == "pipx"

    def test_pipx_on_macos(self):
        pipx_python = "/Users/alice/.local/pipx/venvs/atdd/bin/python3.12"
        with patch("sys.executable", pipx_python):
            assert detect_install_method() == "pipx"


# ---------------------------------------------------------------------------
# Y005-UNIT-002: detect_install_method() returns 'editable' for editable installs
# ---------------------------------------------------------------------------
class TestDetectInstallMethodEditable:
    def test_editable_via_direct_url(self, tmp_path):
        import importlib.metadata as meta

        direct_url_content = '{"url": "file:///home/user/atdd", "dir_info": {"editable": true}}'
        dist_path = tmp_path / "atdd-1.0.dist-info"
        dist_path.mkdir()
        (dist_path / "direct_url.json").write_text(direct_url_content)

        with patch("atdd.version_check._is_editable_install", return_value=True):
            assert detect_install_method() == "editable"

    def test_editable_via_helper_true(self):
        with patch("atdd.version_check._is_editable_install", return_value=True):
            assert detect_install_method() == "editable"


# ---------------------------------------------------------------------------
# Y005-UNIT-003: detect_install_method() returns 'pip' for regular installs
# ---------------------------------------------------------------------------
class TestDetectInstallMethodPip:
    def test_regular_site_packages(self):
        regular_python = "/usr/local/lib/python3.12/site-packages"
        with patch("sys.executable", "/usr/local/bin/python3.12"), \
             patch("atdd.version_check._is_editable_install", return_value=False):
            result = detect_install_method()
            assert result == "pip"

    def test_venv_python_not_pipx(self):
        venv_python = "/home/user/.venv/bin/python"
        with patch("sys.executable", venv_python), \
             patch("atdd.version_check._is_editable_install", return_value=False):
            result = detect_install_method()
            assert result == "pip"


# ---------------------------------------------------------------------------
# Y005-UNIT-004: upgrade_command() returns 'pipx upgrade atdd' for pipx
# ---------------------------------------------------------------------------
class TestUpgradeCommandPipx:
    def test_returns_pipx_command(self):
        with patch("atdd.version_check.detect_install_method", return_value="pipx"):
            assert upgrade_command() == "pipx upgrade atdd"


# ---------------------------------------------------------------------------
# Y005-UNIT-005: upgrade_command() returns pip command for pip installs
# ---------------------------------------------------------------------------
class TestUpgradeCommandPip:
    def test_returns_pip_command(self):
        with patch("atdd.version_check.detect_install_method", return_value="pip"):
            assert upgrade_command() == "pip install --upgrade atdd"


# ---------------------------------------------------------------------------
# Y005-UNIT-006: upgrade_command() returns git pull for editable installs
# ---------------------------------------------------------------------------
class TestUpgradeCommandEditable:
    def test_returns_git_pull_command(self):
        with patch("atdd.version_check.detect_install_method", return_value="editable"):
            cmd = upgrade_command()
            assert "git" in cmd
            assert "pull" in cmd

    def test_unknown_falls_back_to_pip(self):
        with patch("atdd.version_check.detect_install_method", return_value="unknown"):
            cmd = upgrade_command()
            assert "pip install" in cmd or "pipx" in cmd or "git pull" in cmd


# ---------------------------------------------------------------------------
# Y005-UNIT-007: No hardcoded 'pip install --upgrade atdd' in user-facing files
# ---------------------------------------------------------------------------
class TestNoHardcodedPipInstall:
    """Grep the inventory files and assert no hardcoded pip install --upgrade atdd
    outside of auto_upgrade()'s own pip branch.
    """

    REPO_ROOT = Path(__file__).parents[3]  # src/atdd/tests/../../../ = repo root
    PATTERN = re.compile(r"pip install --upgrade atdd")

    def _read(self, rel_path: str) -> str:
        return (self.REPO_ROOT / rel_path).read_text()

    def _extract_auto_upgrade_body(self, source: str) -> tuple[str, str]:
        """Return (before_auto_upgrade, auto_upgrade_body) strings."""
        marker = "def auto_upgrade()"
        idx = source.find(marker)
        if idx == -1:
            return source, ""
        before = source[:idx]
        after = source[idx:]
        # Find next top-level def/class after auto_upgrade
        next_def = re.search(r"\ndef [a-zA-Z_]|\nclass [a-zA-Z_]", after[len(marker):])
        if next_def:
            body = after[: len(marker) + next_def.start()]
            rest = after[len(marker) + next_def.start():]
            return before + rest, body
        return before, after

    def test_version_check_no_hardcode_outside_auto_upgrade(self):
        source = self._read("src/atdd/version_check.py")
        outside, inside = self._extract_auto_upgrade_body(source)
        matches = self.PATTERN.findall(outside)
        assert not matches, (
            f"version_check.py has hardcoded 'pip install --upgrade atdd' outside "
            f"auto_upgrade(): {matches}"
        )

    def test_upgrader_no_hardcoded_pip(self):
        source = self._read("src/atdd/coach/commands/upgrader.py")
        matches = self.PATTERN.findall(source)
        assert not matches, (
            f"upgrader.py still has hardcoded 'pip install --upgrade atdd': {matches}"
        )

    def test_pre_push_hook_no_hardcoded_pip(self):
        source = self._read("src/atdd/coach/templates/hooks/pre-push")
        matches = self.PATTERN.findall(source)
        assert not matches, (
            f"pre-push hook still has hardcoded 'pip install --upgrade atdd': {matches}"
        )

    def test_pre_merge_commit_hook_no_hardcoded_pip(self):
        source = self._read("src/atdd/coach/templates/hooks/pre-merge-commit")
        matches = self.PATTERN.findall(source)
        assert not matches, (
            f"pre-merge-commit hook still has hardcoded 'pip install --upgrade atdd': {matches}"
        )

    def test_issue_body_convention_no_pip_install(self):
        source = self._read("src/atdd/planner/conventions/issue-body.convention.yaml")
        # Match both forms: -U and --upgrade
        pattern = re.compile(r"pip install (-U|--upgrade) atdd")
        matches = pattern.findall(source)
        assert not matches, (
            f"issue-body.convention.yaml has hardcoded pip install: {matches}"
        )


# ---------------------------------------------------------------------------
# Y005-UNIT-008: check_for_updates() uses upgrade_command() in its message
# ---------------------------------------------------------------------------
class TestCheckForUpdatesUsesUpgradeCommand:
    def test_message_contains_upgrade_command_output(self):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")), \
             patch("atdd.version_check.upgrade_command", return_value="pipx upgrade atdd") as mock_cmd, \
             patch("atdd.version_check._load_cache", return_value=None), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.0.0"):
            # check_for_updates may bypass is_outdated; patch _is_newer to trigger update
            with patch("atdd.version_check._is_newer", return_value=True):
                result = check_for_updates()
        assert result is not None
        assert "pipx upgrade atdd" in result, (
            f"Expected 'pipx upgrade atdd' in check_for_updates() output; got: {result!r}"
        )

    def test_message_does_not_hardcode_pip_install(self):
        with patch("atdd.version_check.upgrade_command", return_value="pipx upgrade atdd"), \
             patch("atdd.version_check._is_newer", return_value=True), \
             patch("atdd.version_check._load_cache", return_value=None), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.0.0"):
            result = check_for_updates()
        if result is not None:
            assert "pip install --upgrade atdd" not in result, (
                f"check_for_updates() must not hardcode 'pip install --upgrade atdd'; "
                f"got: {result!r}"
            )


# ---------------------------------------------------------------------------
# Y005-UNIT-009: Upgrader.run() uses upgrade_command() in its prompts/messages
# ---------------------------------------------------------------------------
class TestUpgraderUsesUpgradeCommand:
    def test_prompt_contains_upgrade_command_output(self, capsys, tmp_path):
        from atdd.coach.commands.upgrader import Upgrader

        (tmp_path / ".atdd").mkdir()
        (tmp_path / ".atdd" / "config.yaml").write_text(
            "toolkit:\n  last_version: 3.0.0\n"
        )

        with patch("atdd.coach.commands.upgrader.is_outdated",
                   return_value=(True, "3.0.0", "4.0.0")), \
             patch("atdd.version_check.upgrade_command", return_value="pipx upgrade atdd"), \
             patch("atdd.coach.commands.upgrader.upgrade_command", return_value="pipx upgrade atdd"), \
             patch("atdd.coach.commands.upgrader.auto_upgrade", return_value=True):
            rc = Upgrader(repo_root=tmp_path).run(yes=True)

        out = capsys.readouterr().out
        assert "pipx upgrade atdd" in out, (
            f"Expected 'pipx upgrade atdd' in upgrader output; got: {out!r}"
        )

    def test_output_does_not_hardcode_pip_install(self, capsys, tmp_path):
        from atdd.coach.commands.upgrader import Upgrader

        (tmp_path / ".atdd").mkdir()
        (tmp_path / ".atdd" / "config.yaml").write_text(
            "toolkit:\n  last_version: 3.0.0\n"
        )

        with patch("atdd.coach.commands.upgrader.is_outdated",
                   return_value=(True, "3.0.0", "4.0.0")), \
             patch("atdd.version_check.upgrade_command", return_value="pipx upgrade atdd"), \
             patch("atdd.coach.commands.upgrader.upgrade_command", return_value="pipx upgrade atdd"), \
             patch("atdd.coach.commands.upgrader.auto_upgrade", return_value=True):
            rc = Upgrader(repo_root=tmp_path).run(yes=True)

        out = capsys.readouterr().out
        assert "pip install --upgrade atdd" not in out, (
            f"Upgrader output must not hardcode 'pip install --upgrade atdd'; got: {out!r}"
        )
