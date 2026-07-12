# URN: test:author-atdd-substrate:package-composition:C007-SMOKE-001-validate-package-cli
# Acceptance: acc:author-atdd-substrate:C007-SMOKE-001-validate-package-cli
# WMBT: wmbt:author-atdd-substrate:C007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C007-SMOKE-001 — `atdd validate package <path>` validates a real installed
extension package against core loaded package-relatively from the installed toolkit
(no core checkout), with no runtime execution."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[4]
_REPO = _SRC.parent
_DEMO = pathlib.Path(__file__).resolve().parent / "fixtures" / "packages" / "acme.extension.demo"


def _validate_package(path):
    env = {"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", "")}
    return subprocess.run([sys.executable, "-m", "atdd", "validate", "package", str(path)],
                          capture_output=True, text=True, env=env, timeout=90)


def test_cli_validates_fixture_against_installed_core():
    r = _validate_package(_DEMO)
    assert r.returncode == 0, f"validate package failed: {r.stdout}\n{r.stderr}"
    assert "valid against core" in r.stdout


def test_cli_validates_real_github_extension_if_present():
    candidates = [
        _REPO.parent.parent / "atdd-extensions" / "official" / "atdd.extension.github",
        _REPO.parent / "atdd-extensions" / "official" / "atdd.extension.github",
    ]
    pkg = next((c for c in candidates if c.exists()), None)
    if pkg is None:
        pytest.skip("atdd-extensions not checked out beside core")
    r = _validate_package(pkg)
    assert r.returncode == 0, f"validate package failed on real github extension: {r.stdout}\n{r.stderr}"
    assert "valid against core" in r.stdout
