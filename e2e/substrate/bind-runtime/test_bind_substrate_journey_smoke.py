# URN: test:train:0005-bind-substrate:E2E-001-bind-substrate-journey
# Train: train:0005-bind-substrate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the bind-substrate-runtime train — over a real
#          locked substrate, the real `atdd` CLI composes a digest-keyed binding
#          plan (bind --check) and renders bound-owned vs legacy-fallback
#          capabilities (capabilities). No mocks: real subprocesses, real lockfile,
#          real package-data schema; no implementation code is executed at compose.
"""Train-level E2E: the full `atdd bind --check` -> `atdd capabilities` journey.

Exercises the binding pipeline as a working whole — load enabled packages (L001),
index + resolve workspace/contract (C002), compose + validate the digest-keyed
binding plan (D001), and surface it (binding-cli) — over a real installed substrate
built from the shipped binding-test builders.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))
from atdd.substrate.binding.tests.conftest import (  # noqa: E402
    install_extension,
    install_provider,
)


def _run(args, cwd):
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        "CI": "true",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


def test_bind_then_capabilities_journey(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / ".atdd").mkdir(parents=True)
    install_provider(project)
    install_extension(project, "acme.extension.demo", convention="demo.pr.gate")

    # bind --check composes + writes the digest-keyed binding plan (no execution).
    bind = _run(["--repo", str(project), "bind", "--check"], project)
    assert bind.returncode == 0, bind.stdout + bind.stderr
    assert "1 bound" in bind.stdout
    assert "demo.pr.gate" in bind.stdout
    plan = project / ".atdd" / "binding.lock.yaml"
    assert plan.exists()
    assert "substrate_lock_digest: sha256:" in plan.read_text()

    # capabilities renders the bound capability from the written plan.
    caps = _run(["--repo", str(project), "capabilities"], project)
    assert caps.returncode == 0, caps.stdout + caps.stderr
    assert "bound" in caps.stdout
    assert "demo.pr.gate" in caps.stdout
    assert "acme.extension.demo.gate.impl" in caps.stdout
