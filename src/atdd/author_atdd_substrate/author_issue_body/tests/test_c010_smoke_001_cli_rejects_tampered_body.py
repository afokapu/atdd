# URN: test:author-atdd-substrate:author-issue-body:C010-SMOKE-001-cli-rejects-tampered-body
# Acceptance: acc:author-atdd-substrate:C010-SMOKE-001-cli-rejects-tampered-body
# WMBT: wmbt:author-atdd-substrate:C010
# Phase: SMOKE
# Layer: integration
"""C010-SMOKE-001 — the CLI rejects a tampered (Graph-Context-removed) body.

Live end-to-end via the repo CLI: the schema-driven compliance check, run over a
body whose `### Graph Context` subsection was removed, exits non-zero and names
the missing required section sourced from issue.schema.json.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._helpers import legacy_compliant_body, run_cli


@pytest.mark.smoke
def test_c010_smoke_001_cli_rejects_tampered_body(tmp_path: Path):
    tampered = legacy_compliant_body().replace("### Graph Context", "### Removed Heading")
    body_file = tmp_path / "tampered_issue_body.md"
    body_file.write_text(tampered, encoding="utf-8")

    # Schema-driven compliance check over a local body file. (`--check` is the
    # validate mode of the new `atdd author issue` subcommand, Phase 3 of #1223.)
    proc = run_cli("author", "issue", "--check", str(body_file))

    assert proc.returncode != 0, (
        "CLI accepted a body missing `### Graph Context`\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    combined = proc.stdout + proc.stderr
    assert "Graph Context" in combined, (
        f"CLI output does not name the missing section:\n{combined}"
    )
