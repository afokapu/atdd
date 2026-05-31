# URN: test:govern-lifecycle:define-validator-report-and-persistence-materialization-contract:E037-SMOKE-001-real-collect-reports-emission
# Acceptance: acc:govern-lifecycle:E037-SMOKE-001-real-collect-reports-emission
# WMBT: wmbt:govern-lifecycle:E037
# Phase: RED
# Layer: backend.integration
"""SMOKE test for E037-SMOKE-001 (docs/coach-decomposition.md §4.11).

Exercises the real disposition-gate emission adapter in a real interpreter
subprocess writing to a real on-disk run sink — not an in-memory stub. Proves
that a per-persona validator routing through ``assert_disposition_satisfied``
emits a ``ValidatorReport`` row the train persistence layer can read back.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.atdd_validator

_REPO_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"


def test_real_disposition_gate_emits_validator_report_to_disk(tmp_path):
    sink = tmp_path / "validator-reports.jsonl"
    script = textwrap.dedent(
        f"""
        import os, types
        os.environ["ATDD_VALIDATOR_REPORTS_PATH"] = {str(sink)!r}
        import atdd.coach.utils.disposition_gate as dg
        violation = types.SimpleNamespace(
            rule_id="demo.e037.smoke",
            severity=4,
            location="src/x.py:1",
            detail="smoke violation",
        )
        try:
            # Unknown rule -> strict tier -> gate fails AFTER emission happens.
            dg.assert_disposition_satisfied("e037_smoke_validator", [violation])
        except BaseException:
            pass
        """
    )
    # Ensure the subprocess imports THIS worktree's source (with the emit adapter),
    # not an unrelated installed build.
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(_REPO_SRC), os.environ.get("PYTHONPATH", "")]
        ),
    }
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr

    rows = [json.loads(line) for line in sink.read_text().splitlines() if line.strip()]
    assert any(
        row["rule_id"] == "demo.e037.smoke" and row["disposition"] == "block"
        for row in rows
    ), f"no matching ValidatorReport row emitted; got {rows!r}"
