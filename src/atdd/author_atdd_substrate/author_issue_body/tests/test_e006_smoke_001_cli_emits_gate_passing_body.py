# URN: test:author-atdd-substrate:author-issue-body:E006-SMOKE-001-cli-emits-gate-passing-body
# Acceptance: acc:author-atdd-substrate:E006-SMOKE-001-cli-emits-gate-passing-body
# WMBT: wmbt:author-atdd-substrate:E006
# Phase: SMOKE
# Layer: integration
"""E006-SMOKE-001 — `atdd author issue` emits a gate-passing body, no patching.

Live end-to-end via the repo CLI in a real checkout: `atdd author issue` writes a
schema-valid issue body to stdout, and that emitted body passes the schema-driven
compliance gate with no manual edits.
"""
from __future__ import annotations

import pytest

from ._helpers import get_validate_issue_body, run_cli


@pytest.mark.smoke
def test_e006_smoke_001_cli_emits_gate_passing_body():
    proc = run_cli(
        "author",
        "issue",
        "--title",
        "Live smoke schema-driven issue",
        "--type",
        "implementation",
        "--status",
        "INIT",
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
