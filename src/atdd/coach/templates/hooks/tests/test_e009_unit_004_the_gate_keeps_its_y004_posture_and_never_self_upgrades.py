# URN: test:integration-hardening:run-upgrade-unattended:E009-UNIT-004-the-gate-keeps-its-y004-posture-and-never-self-upgrades
# Acceptance: acc:integration-hardening:E009-UNIT-004-the-gate-keeps-its-y004-posture-and-never-self-upgrades
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E009-UNIT-004 — Y004 is made rarely reached, never relaxed.

RED Test for acc:integration-hardening:E009-UNIT-004-the-gate-keeps-its-y004-posture-and-never-self-upgrades
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E009

``wmbt:integration-hardening:Y004`` states that ``_gate_main`` must never call
``auto_upgrade()`` or run pip from inside the gate, because mutating the system
from a *blocking* hook is unsafe on PEP 668 systems, in virtualenvs and in CI.
That rationale is untouched by #1762 and the boundary stands.

It is precisely the boundary a careless implementation of #1762 would repeal.
Once a working ``self_upgrade()`` exists one line away, the obvious "improvement"
is to call it from the gate too — a change that would pass every functional test
in this repo while silently reinstating the defect #776 closed. This file exists
to make that edit fail.

The safety of the new trigger rests on a property the gate does not have: git
ignores ``post-*`` exit codes and honours ``pre-push``'s. So the test is not
"is upgrading bad" but "does the upgrade only ever run where nothing can be
refused".
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import patch

import pytest

import atdd.version_check as version_check
from atdd.coach.commands import upgrader

pytestmark = [pytest.mark.coach, pytest.mark.platform]

HOOKS_DIR = Path(__file__).resolve().parents[1]
ATDD_PKG = Path(version_check.__file__).resolve().parent

#: Hooks whose exit code git HONOURS. An upgrade reachable from any of these can
#: refuse an operator's operation, which is the whole thing #1762 avoids.
_BLOCKING_HOOKS = ["pre-push", "pre-commit", "commit-msg", "pre-merge-commit", "pre-rebase"]

#: Hooks whose exit code git DISCARDS. The upgrade belongs here and only here.
_NON_BLOCKING_HOOKS = ["post-merge", "post-checkout"]

_SELF_UPGRADE_INVOCATION = re.compile(r"\bself[-_]upgrade\b")


def test_e009_unit_004_the_gate_calls_neither_auto_upgrade_nor_self_upgrade():
    """The gate refuses and names the remedy. It does not become the remedy."""
    with patch.object(version_check, "is_outdated", return_value=(True, "4.38.9", "4.38.10")), \
         patch.object(version_check, "auto_upgrade") as auto, \
         patch.object(upgrader, "self_upgrade") as self_up, \
         pytest.raises(SystemExit) as exc:
        version_check._gate_main()

    assert exc.value.code == 1, f"the gate must still refuse, got exit {exc.value.code}"
    auto.assert_not_called()
    self_up.assert_not_called()


def test_e009_unit_004_the_refusal_still_names_the_remedy(capsys):
    """Y004-UNIT-002's guarantee, restated here so #1762 cannot erode it."""
    with patch.object(version_check, "is_outdated", return_value=(True, "4.38.9", "4.38.10")), \
         pytest.raises(SystemExit):
        version_check._gate_main()

    combined = "".join(capsys.readouterr())
    assert "atdd upgrade" in combined, f"the refusal must name the remedy:\n{combined}"
    assert "pip install" not in combined, f"the gate must not advertise pip:\n{combined}"


def test_e009_unit_004_no_blocking_hook_invokes_the_self_upgrade():
    """The static half: an upgrade must be unreachable from any gating hook.

    Checked in the template source rather than only at runtime, because the
    dangerous version of this change is one line of shell that no unit test
    exercising ``_gate_main`` would ever see.
    """
    offenders = []
    for name in _BLOCKING_HOOKS:
        path = HOOKS_DIR / name
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if _SELF_UPGRADE_INVOCATION.search(code):
                offenders.append(f"{name}:{lineno}: {line.strip()}")

    assert not offenders, (
        "a hook whose exit code git honours can refuse an operator's operation, so "
        "it must not be able to trigger an upgrade (wmbt:integration-hardening:Y004):\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_e009_unit_004_the_non_blocking_hooks_are_where_it_actually_lives():
    """The converse. Y004 would also be satisfied by shipping nothing at all."""
    for name in _NON_BLOCKING_HOOKS:
        text = (HOOKS_DIR / name).read_text(encoding="utf-8")
        assert "atdd self-upgrade" in text, (
            f"{name} does not invoke the self-upgrade, so #1762 shipped inert"
        )
        assert text.rstrip().endswith("exit 0"), (
            f"{name} must end by exiting 0 regardless of what the upgrade did"
        )


def test_e009_unit_004_the_gate_module_cannot_acquire_an_upgrade_trigger():
    """``version_check`` must not import the module that owns the trigger.

    The direction of the dependency is the guarantee: ``upgrader`` imports
    ``version_check``, never the reverse. That is also what keeps this path free
    of ``ProjectInitializer`` / ``AgentConfigSync`` and therefore free of #1703's
    ``init --force`` and its GitHub writes.
    """
    tree = ast.parse((ATDD_PKG / "version_check.py").read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)

    # Prose is not reach: `print_upgrade_sync_notice` recounts #342's
    # AgentConfigSync mistake in its own docstring, and that history is worth
    # keeping. Only a real import can put the behaviour back.
    forbidden = {name for name in imported
                 if "upgrader" in name or name in ("ProjectInitializer", "AgentConfigSync")}
    assert not forbidden, (
        f"version_check.py imports {sorted(forbidden)}; the gate must not be able to "
        "reach the upgrade orchestration, and must not inherit init --force (#1703)"
    )


def test_e009_unit_004_the_upgrade_runs_pip_only_outside_the_gate():
    """Y004-UNIT-005 restated: no pip subprocess anywhere on the gate path."""
    with patch.object(version_check, "is_outdated", return_value=(True, "4.38.9", "4.38.10")), \
         patch("subprocess.run") as spawned, \
         pytest.raises(SystemExit):
        version_check._gate_main()

    for call in spawned.call_args_list:
        argv = " ".join(str(a) for a in (call.args[0] if call.args else []))
        assert "pip" not in argv and "pipx" not in argv, (
            f"the gate spawned an installer: {argv}"
        )
