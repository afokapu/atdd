# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-UNIT-003-registry-check-auto-heals-in-non-ci
# Acceptance: acc:govern-lifecycle:E023-UNIT-003-registry-check-auto-heals-in-non-ci
# WMBT: wmbt:govern-lifecycle:E023
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-003: registry check auto-runs atdd registry update --yes and re-stages
mirror files in non-CI mode instead of blocking.

RED state: The pre-push hook's registry gate currently exits non-zero when drift is
detected and prints an error message — it does NOT auto-fix. This test fails because
the auto-heal behavior is absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-push"

_AUTO_HEAL_MARKERS = [
    "registry update --yes",
    "atdd registry update --yes",
    "auto-resynced",
    "auto_resync",
]


def test_pre_push_hook_has_registry_auto_heal():
    """AC-UNIT-003: pre-push hook must auto-run atdd registry update --yes on drift in non-CI mode."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    has_auto_heal = any(m in hook_text for m in _AUTO_HEAL_MARKERS)
    assert has_auto_heal, (
        f"Pre-push hook at {HOOK_PATH} does not contain registry auto-heal logic.\n"
        "Currently the registry gate blocks with an error when drift is detected.\n"
        "In non-CI mode, the hook should instead:\n"
        "  1. Run: atdd registry update --yes\n"
        "  2. Re-stage: git add plan/_wagons.yaml plan/_trains.yaml contracts/_artifacts.yaml\n"
        "  3. Exit 0 with a notice (issue #845 Item B)."
    )


def test_registry_auto_heal_notice_content():
    """AC-UNIT-003: auto-heal notice must mention 'atdd registry update --yes'."""
    hook_text = HOOK_PATH.read_text(encoding="utf-8")
    if not any(m in hook_text for m in _AUTO_HEAL_MARKERS):
        pytest.skip("Registry auto-heal not yet implemented — RED")

    assert "registry update --yes" in hook_text, (
        "Auto-heal block must mention 'atdd registry update --yes' so the operator\n"
        "can understand what was done automatically (issue #845 Item B)."
    )
