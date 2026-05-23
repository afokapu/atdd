# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-UNIT-002-version-gate-uses-repo-minimum-not-pypi
# Acceptance: acc:govern-lifecycle:E023-UNIT-002-version-gate-uses-repo-minimum-not-pypi
# WMBT: wmbt:govern-lifecycle:E023
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-002: version gate blocks only when installed atdd is older than the repo's
declared minimum_version, not PyPI latest.

RED state: _gate_main() currently compares against PyPI latest. It does not read
minimum_version from .atdd/config.yaml. This test fails because the function
does not accept a minimum_version parameter yet.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]


def test_gate_main_accepts_minimum_version_parameter():
    """AC-UNIT-002: _gate_main must accept a minimum_version parameter."""
    try:
        import inspect
        from atdd.version_check import _gate_main
        sig = inspect.signature(_gate_main)
        params = list(sig.parameters.keys())
        assert "minimum_version" in params or "min_version" in params or "config" in params, (
            "_gate_main does not accept a minimum_version (or min_version/config) parameter.\n"
            "Add: def _gate_main(minimum_version: str | None = None) -> None\n"
            "so the version gate can be tightened to compare against the repo's declared\n"
            "minimum, not PyPI latest (issue #845 Item B)."
        )
    except ImportError:
        pytest.fail("atdd.version_check._gate_main not found — cannot check signature")


def test_gate_main_does_not_block_when_installed_exceeds_minimum():
    """AC-UNIT-002: gate exits 0 when installed >= minimum_version even if behind PyPI latest."""
    try:
        from atdd.version_check import _gate_main
        import inspect
        sig = inspect.signature(_gate_main)
        if "minimum_version" not in sig.parameters and "min_version" not in sig.parameters:
            pytest.skip("minimum_version parameter not yet implemented — RED")
    except ImportError:
        pytest.fail("atdd.version_check._gate_main not found")

    # Should not raise SystemExit when installed >= minimum
    try:
        from atdd.version_check import _gate_main
        _gate_main(minimum_version="0.0.0")  # type: ignore[call-arg]
    except SystemExit as e:
        pytest.fail(
            f"_gate_main raised SystemExit({e.code}) with minimum_version='0.0.0'.\n"
            "When installed version >= minimum_version, _gate_main must exit 0\n"
            "(issue #845 Item B)."
        )
    except TypeError as e:
        pytest.skip(f"minimum_version parameter not yet wired: {e} — RED")
