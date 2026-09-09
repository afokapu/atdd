"""Shared harness for the P002 interpreter-resolution acceptances.

Extracted so UNIT-001 and UNIT-002 can live in their own files — the
validator-binding rule is per FILE header, so one file covering two
acceptances leaves the second one unbound. Modelled on the sibling
`_gh_issue_create_precommit_harness.py`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

HOOKS = Path(__file__).resolve().parents[1]
BRIDGE = "# --- Source-checkout live-source bridge"
BEGIN = "# --- BEGIN atdd-gate-interpreter ---"
END = "# --- END atdd-gate-interpreter ---"
CARRIERS = ("pre-push", "pre-merge-commit")


def _preamble(hook: str) -> str:
    """Bridge + resolution together — they are one unit and share a flag.

    Extracting only the delimited block would miss the flag reset that guards it,
    and a test that set that internal flag by hand would be asserting on the
    implementation's private state instead of the condition it stands for.
    """
    src = (HOOKS / hook).read_text(encoding="utf-8")
    for marker in (BRIDGE, BEGIN, END):
        assert marker in src, f"{hook} is missing {marker!r}"
    return src[src.index(BRIDGE) : src.index(END) + len(END)]


def _block(hook: str) -> str:
    src = (HOOKS / hook).read_text(encoding="utf-8")
    return src[src.index(BEGIN) : src.index(END) + len(END)]


def _toolkit_checkout(tmp_path: Path) -> Path:
    """A tree the bridge will recognise: src/atdd plus an atdd pyproject."""
    root = tmp_path / "toolkit"
    (root / "src" / "atdd").mkdir(parents=True)
    (root / "pyproject.toml").write_text('name = "atdd"\n', encoding="utf-8")
    return root


def _resolve(hook: str, *, repo_root: Path | None, path_dir: Path | None,
             tmp_path: Path, inherited: str = "", want_stderr: bool = False):
    """Run the real preamble under a real sh and report the interpreter chosen."""
    script = tmp_path / "probe.sh"
    prelude = f'_REPO_ROOT="{repo_root or ""}"\n'
    if inherited:
        prelude = f'export _ATDD_SOURCE_BRIDGE="{inherited}"\n' + prelude
    script.write_text(
        f"#!/bin/sh\nset -u\n{prelude}{_preamble(hook)}\n"
        'printf "%s" "$ATDD_PYTHON"\n'
    )
    script.chmod(0o755)

    # A MINIMAL PATH, always: inheriting the caller's would leave the developer's
    # own `atdd` discoverable and quietly turn the no-console-script case into the
    # console-script case — the test would then pass by finding a real install
    # rather than by exercising the fallback.
    env = dict(os.environ)
    env["PATH"] = f"{path_dir}:/usr/bin:/bin" if path_dir else "/usr/bin:/bin"
    proc = subprocess.run(
        ["sh", str(script)], capture_output=True, text=True, env=env, check=True
    )
    return (proc.stdout.strip(), proc.stderr.strip()) if want_stderr else proc.stdout.strip()


def _fake_atdd(tmp_path: Path, interpreter: str) -> Path:
    """A console script shaped like a real one: shebang, `-E`, executable."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    script = d / "atdd"
    script.write_text(f"#!{interpreter} -E\nimport sys\n")
    script.chmod(0o755)
    return d


