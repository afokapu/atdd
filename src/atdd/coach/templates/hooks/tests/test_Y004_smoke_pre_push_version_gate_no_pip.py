# Acceptance: acc:integration-hardening:Y004-SMOKE-001-pre-push-hook-with-outdated-version-exits-1-cleanly
"""SMOKE: pre-push hook version gate exits 1 cleanly — no pip subprocess.

Issue #776: when _gate_main detects an outdated atdd, it must exit 1 with
'atdd upgrade' instruction and must never run 'pip install'. This smoke test
runs _gate_main in a real subprocess with a mocked is_outdated to confirm
the gate's output and exit code against real runtime infrastructure.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[6]


def _run_gate_subprocess() -> subprocess.CompletedProcess:
    """Run _gate_main in a fresh subprocess via a driver script.

    A fresh subprocess is required because:
    - importlib.metadata caches are per-process; a real install check would
      hit PyPI or cache — unreliable in CI.
    - We patch is_outdated at module level so the hook path is exercised
      exactly as it runs from the pre-push shell, just with a mocked oracle.

    PYTHONPATH is prepended with the repo src/ dir so the subprocess loads
    the local development version of atdd, not the installed package.
    """
    driver = textwrap.dedent("""
        import sys
        from unittest.mock import patch

        # Patch is_outdated to simulate the outdated case without hitting PyPI.
        with patch("atdd.version_check.is_outdated", return_value=(True, "3.0.0", "4.0.0")):
            from atdd.version_check import _gate_main
            try:
                _gate_main()
            except SystemExit as e:
                sys.exit(e.code)
    """)
    import os
    env = os.environ.copy()
    src_dir = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}:{existing}" if existing else src_dir
    return subprocess.run(
        [sys.executable, "-c", driver],
        capture_output=True,
        text=True,
        env=env,
    )


class TestVersionGateSmokeNoPip:
    """Y004-SMOKE-001: version gate exits 1 without spawning pip."""

    def test_hook_exits_1_when_outdated(self):
        result = _run_gate_subprocess()
        assert result.returncode == 1, (
            f"Expected exit code 1 when outdated; got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_hook_output_contains_atdd_upgrade(self):
        result = _run_gate_subprocess()
        output = result.stdout + result.stderr
        assert "atdd upgrade" in output, (
            f"Expected 'atdd upgrade' in output; got:\n{output}"
        )

    def test_hook_output_does_not_contain_pip_install(self):
        result = _run_gate_subprocess()
        output = result.stdout + result.stderr
        assert "pip install" not in output, (
            f"Output must not contain 'pip install'; got:\n{output}"
        )

    def test_hook_output_does_not_contain_upgrading(self):
        result = _run_gate_subprocess()
        output = result.stdout + result.stderr
        assert "Upgrading..." not in output, (
            f"Output must not contain 'Upgrading...' (removed with auto_upgrade); got:\n{output}"
        )

    def test_hook_output_mentions_latest_version(self):
        result = _run_gate_subprocess()
        output = result.stdout + result.stderr
        assert "4.0.0" in output, (
            f"Expected latest version '4.0.0' in gate output; got:\n{output}"
        )
