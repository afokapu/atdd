# Acceptance: acc:integration-hardening:Y005-SMOKE-001-pipx-install-detection-end-to-end
"""SMOKE tests for install-method-aware upgrade messaging (issue #782).

Verifies detect_install_method() and upgrade_command() work end-to-end
with a simulated pipx executable path.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.version_check import detect_install_method, upgrade_command


class TestPipxDetectionEndToEnd:
    """Y005-SMOKE-001: end-to-end pipx detection without heavy mocking."""

    def test_pipx_path_gives_pipx_upgrade_command(self):
        pipx_python = "/home/user/.local/pipx/venvs/atdd/bin/python"
        with patch("sys.executable", pipx_python), \
             patch("atdd.version_check._is_editable_install", return_value=False):
            method = detect_install_method()
            cmd = upgrade_command()
        assert method == "pipx", f"Expected 'pipx', got {method!r}"
        assert cmd == "pipx upgrade atdd", f"Expected 'pipx upgrade atdd', got {cmd!r}"

    def test_regular_python_gives_pip_upgrade_command(self):
        regular_python = "/usr/bin/python3"
        with patch("sys.executable", regular_python), \
             patch("atdd.version_check._is_editable_install", return_value=False):
            method = detect_install_method()
            cmd = upgrade_command()
        assert method == "pip", f"Expected 'pip', got {method!r}"
        assert "pip install --upgrade atdd" in cmd

    def test_editable_install_gives_git_pull_command(self):
        with patch("atdd.version_check._is_editable_install", return_value=True):
            method = detect_install_method()
            cmd = upgrade_command()
        assert method == "editable", f"Expected 'editable', got {method!r}"
        assert "git" in cmd and "pull" in cmd, (
            f"Expected git pull command for editable install, got {cmd!r}"
        )
