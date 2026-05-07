"""Tests for src/atdd/version_check.py — auto_upgrade PEP 668 fallback +
PyPI propagation-window cache-bust.

Six-cell matrix for ``auto_upgrade``:
  1. Clean happy path (pip succeeds + verify passes).
  2. PEP 668 first-attempt refusal + retry-with-flag success + verify pass.
  3. Stale-cache: returncode=0 + verify fails on attempt 1 → pinned retry → verify passes.
  4. PEP 668 + stale-cache combined (both retry dimensions on each attempt).
  5. Pinned retry also fails → False.
  6. ``expected=None`` (PyPI unreachable) → returncode alone decides.

Plus a dedicated ``_verify_installed_version`` timeout test.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from atdd.version_check import (
    _is_pep668_error,
    _run_with_pep668_retry,
    _verify_installed_version,
    auto_upgrade,
)


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


class TestVerifyInstalledVersion:
    def test_returns_true_when_expected_is_none(self):
        # No target → no check.
        assert _verify_installed_version(None) is True

    def test_returns_true_when_expected_is_empty(self):
        assert _verify_installed_version("") is True

    def test_returns_true_on_subprocess_match(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3.7.2\n")
            assert _verify_installed_version("3.7.2") is True

    def test_returns_false_on_subprocess_mismatch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3.7.1\n")
            assert _verify_installed_version("3.7.2") is False

    def test_returns_false_on_subprocess_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert _verify_installed_version("3.7.2") is False

    def test_returns_false_on_subprocess_timeout(self):
        # TimeoutExpired must not crash auto_upgrade — it must surface as False.
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
            assert _verify_installed_version("3.7.2") is False

    def test_passes_timeout_kwarg(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3.7.2\n")
            _verify_installed_version("3.7.2")
            assert mock_run.call_args.kwargs.get("timeout") == 10


class TestRunWithPep668Retry:
    def test_success_first_try(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            ok, _stderr = _run_with_pep668_retry(["pip", "install", "x"])
            assert ok is True
            assert mock_run.call_count == 1

    def test_retries_on_pep668(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
            ]
            ok, _stderr = _run_with_pep668_retry(["pip", "install", "x"])
            assert ok is True
            assert mock_run.call_count == 2
            assert "--break-system-packages" in mock_run.call_args_list[1].args[0]

    def test_no_retry_on_unrelated_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="other error")
            ok, _stderr = _run_with_pep668_retry(["pip", "install", "x"])
            assert ok is False
            assert mock_run.call_count == 1


class TestAutoUpgrade:
    """Six-cell matrix for the cache-bust + verify behavior."""

    def test_cell1_clean_happy_path(self):
        """returncode=0 on attempt 1 + verify passes → True, single pip call."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is True
            assert mock_run.call_count == 1
            # --no-cache-dir always present.
            assert "--no-cache-dir" in mock_run.call_args_list[0].args[0]

    def test_cell2_pep668_retry_first_attempt(self):
        """PEP 668 refusal → --break-system-packages retry → verify passes."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
            ]
            assert auto_upgrade() is True
            assert mock_run.call_count == 2
            assert "--break-system-packages" in mock_run.call_args_list[1].args[0]
            # No pinned attempt fired.
            for call in mock_run.call_args_list:
                assert "atdd==3.7.2" not in call.args[0]

    def test_cell3_stale_cache_triggers_pinned_retry(self):
        """returncode=0 but verify fails → pinned attempt → verify passes."""
        verify_results = [False, True]  # attempt 1 verify fails; attempt 2 verify passes
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is True
            # Two pip calls: name-only, then pinned.
            assert mock_run.call_count == 2
            assert "atdd" in mock_run.call_args_list[0].args[0]
            assert "atdd==3.7.2" in mock_run.call_args_list[1].args[0]

    def test_cell4_pep668_plus_stale_cache_combined(self):
        """Both retry dimensions on attempt 1, then pinned attempt also clean."""
        verify_results = [False, True]
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # Attempt 1: PEP 668 refusal then BSP success (verify still fails).
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
                # Attempt 2 (pinned): clean.
                MagicMock(returncode=0, stderr=""),
            ]
            assert auto_upgrade() is True
            assert mock_run.call_count == 3
            assert "--break-system-packages" in mock_run.call_args_list[1].args[0]
            assert "atdd==3.7.2" in mock_run.call_args_list[2].args[0]

    def test_cell5_pinned_retry_also_fails(self):
        """First attempt verify-fails, pinned attempt also verify-fails → False."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=[False, False]), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is False
            assert mock_run.call_count == 2

    def test_cell5b_pinned_attempt_pip_failure(self):
        """First attempt verify-fails, pinned attempt pip-fails (e.g., 404) → False."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=[False]), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stderr=""),
                MagicMock(returncode=1, stderr="ERROR: No matching distribution"),
            ]
            assert auto_upgrade() is False
            assert mock_run.call_count == 2

    def test_cell6_expected_none_returncode_decides(self):
        """PyPI unreachable (target=None) → returncode alone decides; no verify-fail path."""
        with patch("atdd.version_check._fetch_latest_version", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is True
            assert mock_run.call_count == 1
            # No pinned attempt — we have nothing to pin to.
            for call in mock_run.call_args_list:
                assert not any("atdd==" in str(arg) for arg in call.args[0])

    def test_cell6b_expected_none_pip_fails(self):
        """target=None and pip fails (no PEP 668) → False, no pinned retry."""
        with patch("atdd.version_check._fetch_latest_version", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="ERROR: Could not find a version that satisfies the requirement atdd",
            )
            assert auto_upgrade() is False
            assert mock_run.call_count == 1

    def test_returns_false_on_subprocess_exception(self):
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("subprocess.run", side_effect=OSError("boom")):
            assert auto_upgrade() is False

    def test_no_cache_dir_always_present(self):
        """Regression: --no-cache-dir on every pip invocation."""
        verify_results = [False, True]
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            auto_upgrade()
            for call in mock_run.call_args_list:
                assert "--no-cache-dir" in call.args[0], \
                    f"--no-cache-dir missing from {call.args[0]}"

    def test_lived_3_7_1_to_3_7_2_regression(self):
        """Regression test reproducing the lived case (issue #455).

        PyPI's JSON API reports 3.7.2 but pip's resolver serves stale 3.7.1
        on the name-only attempt (returncode=0, "Requirement already satisfied").
        Verify catches the mismatch; pinned retry installs 3.7.2.
        """
        verify_results = [False, True]  # name-only got 3.7.1; pinned got 3.7.2
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results) as mock_verify, \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stderr="",
                stdout="Requirement already satisfied: atdd 3.7.1",
            )
            assert auto_upgrade() is True
            # Verify was called with "3.7.2" both times.
            for call in mock_verify.call_args_list:
                assert call.args[0] == "3.7.2"
            # Pinned attempt fired with the correct version.
            assert "atdd==3.7.2" in mock_run.call_args_list[1].args[0]
