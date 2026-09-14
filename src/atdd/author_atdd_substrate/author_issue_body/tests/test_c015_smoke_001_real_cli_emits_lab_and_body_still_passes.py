# URN: test:author-atdd-substrate:author-issue-body:C015-SMOKE-001-real-cli-emits-lab-and-body-still-passes
# Acceptance: acc:author-atdd-substrate:C015-SMOKE-001-real-cli-emits-lab-and-body-still-passes
# WMBT: wmbt:author-atdd-substrate:C015
# Phase: SMOKE
# Layer: integration
"""C015-SMOKE-001 — the REAL `atdd author issue` emits the scaffold, gate-clean.

Everything else about C015 is asserted against ``create_issue_body`` in-process.
This is the only proof that the CLI a person actually types produces the same thing:
a real subprocess, a real temp Control Root, a stubbed ``gh`` so nothing is filed,
and the body read off stdout exactly as an operator would see it.

Mirrors E006-SMOKE-001's scaffolding deliberately — same stub, same control root,
same ``run_cli`` — because that smoke already proves the generate path works
end-to-end, and this one only adds the question of whether `## Lab` rides along
without costing the body its gate-clean status.
"""
from __future__ import annotations

import os
import stat

import pytest

from ._helpers import get_validate_issue_body, run_cli

_SUBSECTIONS = ("Hypothesis", "Setup", "Measured result", "What it changed about the plan")


def _stub_gh_on_path(tmp_path):
    """A fake ``gh`` that drains stdin and prints a canned issue URL."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null 2>&1 || true\n"
        "echo 'https://github.com/afokapu/atdd/issues/999999'\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"


@pytest.mark.smoke
def test_c015_smoke_001_real_cli_emits_lab_and_body_still_passes(tmp_path):
    proc = run_cli(
        "author", "issue",
        "--title", "Live smoke lab scaffold issue",
        "--type", "implementation",
        "--status", "INIT",
        "--slug", "live-smoke-lab-scaffold-issue",
        env={
            "ATDD_CONTROL_ROOT": str(tmp_path / "control"),
            "PATH": _stub_gh_on_path(tmp_path),
        },
    )
    assert proc.returncode == 0, (
        f"`atdd author issue` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    body = proc.stdout
    assert "## Lab" in body, (
        "the real CLI does not emit `## Lab` — #1950 GREEN. In-process coverage is "
        "not enough here: the scaffold has to reach the body an operator is handed."
    )
    for name in _SUBSECTIONS:
        assert f"### {name}" in body, f"`### {name}` missing from the CLI-emitted body"

    # The section rides along without costing the body its gate-clean status.
    violations = get_validate_issue_body()(body)
    assert violations == [], f"CLI-emitted body failed the schema gate: {violations}"
