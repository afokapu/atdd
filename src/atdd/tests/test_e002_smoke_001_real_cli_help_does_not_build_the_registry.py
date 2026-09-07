# URN: test:implement-code:cli-import-cost:E002-SMOKE-001-real-cli-help-does-not-build-the-registry
# Acceptance: acc:implement-code:E002-SMOKE-001-real-cli-help-does-not-build-the-registry
# WMBT: wmbt:implement-code:E002
# Phase: SMOKE
# Layer: integration
"""E002-SMOKE-001 — the real CLI answers --help without building the registry.

UNIT-001 imports ``atdd.cli`` directly. This goes through the real entrypoint
(``python -m atdd --help``) as a subprocess, so the guard holds through actual
argparse dispatch and not merely under a bare import — the path every git hook
takes, four times a commit.

``-X importtime`` reports every module the interpreter actually imported, on
stderr, which makes the assertion a fact about the real process rather than an
inference from timing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_e002_smoke_001_real_cli_help_does_not_build_the_registry():
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "atdd", "--help"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"`atdd --help` failed: {proc.stderr[-2000:]}"
    assert "usage" in proc.stdout.lower(), "no help text was produced"

    offenders = sorted(
        {
            line.rsplit("|", 1)[-1].strip()
            for line in proc.stderr.splitlines()
            if "artifact_claims" in line
        }
    )
    assert offenders == [], (
        "`atdd --help` built the convention registry on the way to printing help: "
        f"{offenders}. Help needs no rule binding; the import belongs at the call "
        "site that does."
    )
