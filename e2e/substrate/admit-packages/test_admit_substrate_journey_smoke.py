# URN: test:train:0004-admit-substrate:E2E-001-admit-substrate-journey
# Train: train:0004-admit-substrate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end journey for the admit-substrate train — the real `atdd`
#          CLI searches a configured registry, admits a real package (validate ->
#          compose -> digest -> install -> lock), lists the locked substrate, and
#          removes it. No mocks: real subprocesses, real schemas, real lockfile,
#          and the admitted package's implementation code is never executed.
"""Train-level E2E: the full `atdd search/add/list/remove` admission journey.

Exercises the whole capability in one flow — schemas (D001), search (L001),
validate+compose without execution (C001/C003), install+digest+lock+list (E001),
remove (C004) — proving the admission front door composes into a working journey.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
FIXTURES = SRC / "atdd" / "substrate" / "tests" / "fixtures"
VALID_EXT = FIXTURES / "valid_extension"
REGISTRY = FIXTURES / "registry"


def _run(args, cwd):
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        "CI": "true",
    }
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def _write_substrate(project: Path) -> None:
    atdd_dir = project / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    (atdd_dir / "substrate.yaml").write_text(
        textwrap.dedent(
            f"""\
            schema_version: "1.0.0"
            registries:
              - id: test.local
                type: path
                source: "{REGISTRY}"
                path: index.yaml
                trust: local
            """
        ),
        encoding="utf-8",
    )


def test_admit_substrate_full_journey(tmp_path) -> None:
    project = tmp_path
    _write_substrate(project)

    # 1. search — locate an artifact in the configured registry (installs nothing)
    found = _run(["search", "demo"], project)
    assert found.returncode == 0, found.stdout + found.stderr
    assert "acme.extension.demo" in found.stdout
    assert not (project / ".atdd" / "extensions").exists()

    # 2. add — admit a real package: validate -> compose -> digest -> install -> lock
    added = _run(["add", "--path", str(VALID_EXT)], project)
    assert added.returncode == 0, added.stdout + added.stderr
    home = project / ".atdd" / "extensions" / "acme.extension.demo" / "0.1.0"
    assert home.is_dir() and (home / "atdd.extension.yaml").exists()
    lock = project / ".atdd" / "substrate.lock.yaml"
    assert lock.exists() and "sha256:" in lock.read_text()

    # 3. list — render the installed substrate from the lockfile
    listed = _run(["list", "--substrate"], project)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "acme.extension.demo" in listed.stdout and "sha256:" in listed.stdout

    # 4. remove — withdraw the artifact; the lock no longer carries it
    removed = _run(["remove", "acme.extension.demo"], project)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert "acme.extension.demo" not in lock.read_text()
