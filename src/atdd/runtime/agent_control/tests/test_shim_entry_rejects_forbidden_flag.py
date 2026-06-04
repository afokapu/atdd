# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E014-UNIT-006-runtime-shim-entry-rejects-forbidden-flag
# Acceptance: acc:govern-lifecycle:E014-UNIT-006-runtime-shim-entry-rejects-forbidden-flag
# WMBT: wmbt:govern-lifecycle:E014
# Phase: GREEN
"""acc:govern-lifecycle:E014-UNIT-006 — the runtime shim CLI entry point
(`python -m atdd.runtime.agent_control`) refuses an adapter command carrying the
forbidden flag before spawning any process.

#969 defense-in-depth: this is the last-mile launch path. In production the
adapter argv is built by the guarded coach-side spawn adapter, but the process-
spawn boundary itself must also refuse the E014-forbidden flag so NO runtime
launch path can emit it — regardless of who assembled argv.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr

from atdd.runtime.agent_control.__main__ import main


def test_shim_main_rejects_forbidden_flag_without_spawning(tmp_path):
    """main() exits non-zero and names the flag; no process is launched."""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        rc = main(
            [
                "--agent-id",
                "e014-unit-006",
                "--runtime-dir",
                str(tmp_path),
                "--",
                "claude",
                "--dangerously-skip-permissions",
            ]
        )

    assert rc != 0, "shim must exit non-zero when the forbidden flag is present"
    assert "--dangerously-skip-permissions" in stderr.getvalue(), stderr.getvalue()
    # No agent runtime artifacts should have been created — the launch was refused.
    assert not (tmp_path / "agents" / "e014-unit-006").exists()
