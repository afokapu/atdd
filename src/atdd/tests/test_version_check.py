"""Tests for src/atdd/version_check.py — auto_upgrade PEP 668 fallback."""
from unittest.mock import MagicMock, patch

import pytest

from atdd.version_check import _is_pep668_error, auto_upgrade


class TestIsPep668Error:
    def test_detects_homebrew_message(self):
        msg = "error: externally-managed-environment\n"
        assert _is_pep668_error(msg) is True

    def test_detects_debian_message(self):
        msg = "error: externally-managed\n"
        assert _is_pep668_error(msg) is True

    def test_returns_false_for_unrelated_error(self):
        msg = "ERROR: Could not find a version that satisfies the requirement atdd"
        assert _is_pep668_error(msg) is False

    def test_returns_false_for_empty(self):
        assert _is_pep668_error("") is False


class TestAutoUpgrade:
    def test_returns_true_on_first_pip_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is True
            assert mock_run.call_count == 1

    def test_returns_false_on_pip_failure_without_pep668(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="ERROR: Could not find a version that satisfies the requirement atdd",
            )
            assert auto_upgrade() is False
            assert mock_run.call_count == 1, "Should not retry for non-PEP-668 errors"

    def test_retries_with_break_system_packages_on_pep668(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
            ]
            assert auto_upgrade() is True
            assert mock_run.call_count == 2

            # Second call must include --break-system-packages
            second_call_args = mock_run.call_args_list[1].args[0]
            assert "--break-system-packages" in second_call_args

    def test_returns_false_if_pep668_retry_also_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=1, stderr="some other error"),
            ]
            assert auto_upgrade() is False
            assert mock_run.call_count == 2

    def test_returns_false_on_subprocess_exception(self):
        with patch("subprocess.run", side_effect=OSError("boom")):
            assert auto_upgrade() is False
