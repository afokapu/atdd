# URN: test:implement-code:cli-import-cost:E002-UNIT-001-cli-import-pulls-no-rule-binding
# Acceptance: acc:implement-code:E002-UNIT-001-cli-import-pulls-no-rule-binding
# WMBT: wmbt:implement-code:E002
# Phase: RED
# Layer: application
"""E002-UNIT-001 — importing the CLI must not drag the convention registry in.

``artifact_claims`` calls ``bind_rule`` at module scope, and the first such call
builds the whole convention registry (~1.5s). ``atdd.cli`` reached it through
``atdd.coach.commands.issue``, so every invocation paid that before argparse had
even chosen a subcommand.

Runs in a FRESH interpreter on purpose: by the time pytest executes this, the
test session has long since imported these modules, so an in-process
``sys.modules`` check would pass no matter what the CLI does.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Importing any of these builds the rule registry. None belongs in CLI startup.
_REGISTRY_MODULES = ("atdd.coach.utils.artifact_claims",)

_PROBE = """
import sys
import atdd.cli  # noqa: F401
print(",".join(m for m in sys.modules if "artifact_claims" in m))
"""


def test_e002_unit_001_cli_import_pulls_no_rule_binding():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"probe failed: {proc.stderr}"

    leaked = [m for m in proc.stdout.strip().split(",") if m]
    assert leaked == [], (
        "importing atdd.cli pulled in rule-binding module(s), so every CLI "
        f"invocation rebuilds the convention registry: {leaked}. "
        "Defer the import to the call site that needs it — do not make bind_rule "
        "lazy, since failing loudly at import is deliberate (SPEC-COACH-RULEID-0007)."
    )
