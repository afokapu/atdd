# Acceptance: acc:integration-hardening:Y004-UNIT-001-gate-never-calls-auto-upgrade
# Acceptance: acc:integration-hardening:Y004-UNIT-002-gate-prints-upgrade-instruction
# Acceptance: acc:integration-hardening:Y004-UNIT-003-gate-allows-when-up-to-date
# Acceptance: acc:integration-hardening:Y004-UNIT-004-gate-skips-when-pypi-unreachable
# Acceptance: acc:integration-hardening:Y004-UNIT-005-no-pip-subprocess-in-gate-path
"""Unit tests for _gate_main() — version gate must not call auto_upgrade().

Issue #776: the pre-push version gate ran pip install inside a git hook,
which is unsafe on PEP 668 systems, inside virtualenvs, and in CI.
The gate must only check and exit 1 with an 'atdd upgrade' instruction.
"""
from __future__ import annotations

import subprocess
import sys
from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest

from atdd.version_check import _gate_main


class TestGateNeverCallsAutoUpgrade:
    """Y004-UNIT-001: _gate_main must never call auto_upgrade() when outdated."""

    def test_auto_upgrade_not_called_when_outdated(self):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")), \
             patch("atdd.version_check.auto_upgrade") as mock_upgrade, \
             pytest.raises(SystemExit):
            _gate_main()
        mock_upgrade.assert_not_called()

    def test_auto_upgrade_not_called_when_up_to_date(self):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "4.0.0")), \
             patch("atdd.version_check.auto_upgrade") as mock_upgrade:
            _gate_main()
        mock_upgrade.assert_not_called()

    def test_auto_upgrade_not_called_when_pypi_unreachable(self):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "")), \
             patch("atdd.version_check.auto_upgrade") as mock_upgrade:
            _gate_main()
        mock_upgrade.assert_not_called()


class TestGatePrintsUpgradeInstruction:
    """Y004-UNIT-002: when outdated, _gate_main prints 'atdd upgrade' instruction."""

    def test_prints_atdd_upgrade_instruction(self, capsys):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")), \
             pytest.raises(SystemExit):
            _gate_main()
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "atdd upgrade" in output, (
            f"Expected 'atdd upgrade' in output; got:\n{output}"
        )

    def test_prints_latest_version(self, capsys):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")), \
             pytest.raises(SystemExit):
            _gate_main()
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "4.0.0" in output, (
            f"Expected latest version '4.0.0' in output; got:\n{output}"
        )

    def test_does_not_print_pip_install(self, capsys):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")), \
             pytest.raises(SystemExit):
            _gate_main()
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "pip install" not in output, (
            f"Output must not contain 'pip install'; got:\n{output}"
        )

    def test_exits_with_code_1_when_outdated(self):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")):
            with pytest.raises(SystemExit) as exc_info:
                _gate_main()
        assert exc_info.value.code == 1


class TestGateAllowsWhenUpToDate:
    """Y004-UNIT-003: _gate_main exits 0 when up to date."""

    def test_no_exit_when_up_to_date(self):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "4.0.0")):
            _gate_main()  # must not raise

    def test_prints_up_to_date_message(self, capsys):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "4.0.0")):
            _gate_main()
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "up to date" in output.lower() or "4.0.0" in output, (
            f"Expected up-to-date confirmation in output; got:\n{output}"
        )


class TestGateSkipsWhenPyPIUnreachable:
    """Y004-UNIT-004: _gate_main exits 0 with a warning when PyPI is unreachable."""

    def test_no_exit_1_when_pypi_unreachable(self):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "")):
            _gate_main()  # must not raise SystemExit(1)

    def test_prints_warning_when_pypi_unreachable(self, capsys):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "")):
            _gate_main()
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert output.strip(), "Expected some output when PyPI is unreachable"


class TestGateNoPipSubprocess:
    """Y004-UNIT-005: _gate_main must not spawn any pip subprocess."""

    def test_no_subprocess_run_with_pip(self):
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")), \
             patch("subprocess.run") as mock_subproc, \
             pytest.raises(SystemExit):
            _gate_main()
        for c in mock_subproc.call_args_list:
            cmd = c.args[0] if c.args else []
            cmd_str = " ".join(str(x) for x in cmd)
            assert "pip" not in cmd_str and "install" not in cmd_str, (
                f"_gate_main spawned a pip/install subprocess: {cmd_str}"
            )

    def test_no_subprocess_run_when_up_to_date(self):
        with patch("atdd.version_check.is_outdated", return_value=(False, "4.0.0", "4.0.0")), \
             patch("subprocess.run") as mock_subproc:
            _gate_main()
        mock_subproc.assert_not_called()
