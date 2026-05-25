# URN: test:govern-lifecycle:smoke-false-green-prevention:E027-SMOKE-001-audit-covers-all-current-smoke-acceptances
# Acceptance: acc:govern-lifecycle:E027-SMOKE-001-audit-covers-all-current-smoke-acceptances
# WMBT: wmbt:govern-lifecycle:E027
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
SMOKE: docs/smoke-audit.md must contain a row for every phase:SMOKE acceptance
found in plan/*.yaml files.  Scans plan/ YAMLs directly (atdd repo graph
returns wagon-level nodes, not individual acceptance URNs).
"""
from __future__ import annotations

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.smoke, pytest.mark.platform]


def _collect_smoke_urns(plan_dir) -> list[str]:
    urns: list[str] = []
    for f in sorted(plan_dir.rglob("*.yaml")):
        if f.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(f.read_text())
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        for acc in raw.get("acceptances", []):
            identity = acc.get("identity", {})
            urn = identity.get("urn", "")
            phase = identity.get("phase", "")
            if phase == "SMOKE" or "-SMOKE-" in urn:
                urns.append(urn)
    return urns


def test_audit_covers_all_current_smoke_acceptances():
    """Every phase:SMOKE acceptance URN in plan/ has a row in docs/smoke-audit.md."""
    repo_root = find_repo_root()
    audit_path = repo_root / "docs" / "smoke-audit.md"
    assert audit_path.exists(), (
        "docs/smoke-audit.md does not exist. Run E027 GREEN phase first."
    )

    plan_dir = repo_root / "plan"
    smoke_urns = _collect_smoke_urns(plan_dir)
    assert smoke_urns, "No SMOKE acceptances found in plan/ — check plan directory path."

    content = audit_path.read_text()
    missing = [u for u in sorted(smoke_urns) if u not in content]

    assert not missing, (
        f"docs/smoke-audit.md is missing rows for {len(missing)} SMOKE acceptance(s):\n"
        + "\n".join(f"  {u}" for u in missing)
        + "\n\nAdd a row for each URN to the Classification Table in docs/smoke-audit.md."
    )
