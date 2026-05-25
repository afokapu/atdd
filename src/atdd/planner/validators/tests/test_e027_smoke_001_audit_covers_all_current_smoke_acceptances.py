# URN: test:govern-lifecycle:smoke-false-green-prevention:E027-SMOKE-001-audit-covers-all-current-smoke-acceptances
# Acceptance: acc:govern-lifecycle:E027-SMOKE-001-audit-covers-all-current-smoke-acceptances
# WMBT: wmbt:govern-lifecycle:E027
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: docs/smoke-audit.md must contain a row for every phase:SMOKE acceptance
returned by `atdd repo graph`.  Currently fails because docs/smoke-audit.md
does not yet exist (E027 GREEN phase must run first).
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.smoke, pytest.mark.platform]


def test_audit_covers_all_current_smoke_acceptances():
    """Every phase:SMOKE acceptance URN from atdd repo graph has a row in docs/smoke-audit.md."""
    repo_root = find_repo_root()
    audit_path = repo_root / "docs" / "smoke-audit.md"
    assert audit_path.exists(), (
        "docs/smoke-audit.md does not exist. Run E027 GREEN phase first."
    )

    result = subprocess.run(
        [sys.executable, "-m", "atdd.cli", "repo", "graph"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"atdd repo graph failed: {result.stderr}"
    )

    raw = result.stdout
    if raw.startswith("⚠"):
        # strip upgrade warning line
        raw = "\n".join(ln for ln in raw.splitlines() if not ln.startswith("⚠"))

    graph = json.loads(raw)
    content = audit_path.read_text()

    missing: list[str] = []
    for urn, node in graph.get("tree", {}).items():
        if not urn.startswith("acc:"):
            continue
        if node.get("phase") == "SMOKE" or "-SMOKE-" in urn:
            if urn not in content:
                missing.append(urn)

    assert not missing, (
        f"docs/smoke-audit.md is missing rows for {len(missing)} SMOKE acceptance(s):\n"
        + "\n".join(f"  {u}" for u in sorted(missing))
    )
