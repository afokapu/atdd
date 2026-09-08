# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-006-runnable-does-not-become-automatic
# Acceptance: acc:integration-hardening:Y007-UNIT-006-runnable-does-not-become-automatic
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-006 — removing a barrier must not grant licence to upgrade unbidden.

RED Test for acc:integration-hardening:Y007-UNIT-006-runnable-does-not-become-automatic
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: The pre-push gate keeps refusing and naming the remedy, and nothing
acquires a self-triggered upgrade. Whether an agent SHOULD upgrade is left to
the autonomy axis (#1626).

TESTER NOTE (#1628): a regression guard, not a first-failing test. Y004 already
shipped this behaviour; the risk it covers is that the obvious "fix" for #1628
is to make the push gate upgrade itself, which would silently repeal Y004.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import atdd.version_check as version_check

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_y007_unit_006_gate_still_refuses_without_upgrading(capsys):
    with patch.object(version_check, "is_outdated", return_value=(True, "3.106.0", "4.27.0")), \
         patch.object(version_check, "auto_upgrade") as mock_upgrade:
        with pytest.raises(SystemExit) as exc:
            version_check._gate_main()

    assert exc.value.code == 1, f"the gate must still refuse, got exit {exc.value.code}"
    mock_upgrade.assert_not_called()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "atdd upgrade" in combined, (
        f"the refusal must still name the remedy; output was:\n{combined}"
    )


@pytest.mark.platform
def test_y007_unit_006_only_the_cli_invokes_the_upgrader():
    """No hook, gate, or lifecycle transition may call Upgrader.run()."""
    src = Path(__file__).resolve().parents[4] / "atdd"
    assert src.is_dir(), f"could not locate the atdd package root at {src}"

    callers = []
    for path in sorted(src.rglob("*.py")):
        if "/tests/" in str(path) or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Upgrader(" in text and "upgrader.py" not in path.name:
            callers.append(path.relative_to(src).as_posix())

    assert callers == ["cli.py"], (
        "the only caller of Upgrader must remain the `atdd upgrade` CLI handler; "
        f"found: {callers}"
    )
