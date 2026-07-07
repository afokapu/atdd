# URN: test:author-atdd-substrate:author-issue-body:E006-SMOKE-001-cli-emits-gate-passing-body
# Acceptance: acc:author-atdd-substrate:E006-SMOKE-001-cli-emits-gate-passing-body
# WMBT: wmbt:author-atdd-substrate:E006
# Phase: SMOKE
# Layer: integration
"""E006-SMOKE-001 — `atdd author issue` emits a gate-passing body, no patching.

Live end-to-end via the repo CLI in a real checkout: `atdd author issue` writes a
schema-valid issue body to stdout, and that emitted body passes the schema-driven
compliance gate with no manual edits.

Since #1272 the generate path also PUBLISHES store-first, so the smoke runs
against a temp ATDD Control Root with a stubbed ``gh`` on PATH — it exercises the
real CLI end-to-end without filing a real GitHub issue. The body-on-stdout +
gate-passing assertions are unchanged.
"""
from __future__ import annotations

import os
import stat

import pytest

from ._helpers import get_validate_issue_body, run_cli


def _stub_gh_on_path(tmp_path):
    """Write a fake ``gh`` that prints a canned issue URL; return a PATH prefix."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    # `gh issue create … --body-file -` must drain stdin (the body) then print a URL.
    gh.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null 2>&1 || true\n"
        "echo 'https://github.com/afokapu/atdd/issues/999999'\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"


@pytest.mark.smoke
def test_e006_smoke_001_cli_emits_gate_passing_body(tmp_path):
    env = {
        "ATDD_CONTROL_ROOT": str(tmp_path / "control"),
        "PATH": _stub_gh_on_path(tmp_path),
    }
    proc = run_cli(
        "author",
        "issue",
        "--title",
        "Live smoke schema-driven issue",
        "--type",
        "implementation",
        "--status",
        "INIT",
        "--slug",
        "live-smoke-schema-driven-issue",
        env=env,
    )

    assert proc.returncode == 0, (
        f"`atdd author issue` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    body = proc.stdout
    assert "### Graph Context" in body
    assert "### Mirror Across Agents" in body

    # The emitted body passes the schema-driven gate untouched.
    violations = get_validate_issue_body()(body)
    assert violations == [], f"CLI-emitted body failed the gate: {violations}"
