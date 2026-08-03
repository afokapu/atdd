# URN: test:integration-hardening:run-upgrade-unattended:E008-UNIT-006-two-sequential-runs-converge-and-the-first-names-the-second
# Acceptance: acc:integration-hardening:E008-UNIT-006-two-sequential-runs-converge-and-the-first-names-the-second
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-006 — the two-step shape is kept, and it converges unattended.

RED Test for acc:integration-hardening:E008-UNIT-006-two-sequential-runs-converge-and-the-first-names-the-second
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E008
Purpose: Operator decision on #1628 — keep the existing two-step contract; the
process that ran pip is still running the old code, so it reports and exits and
the caller takes the second step. Self-exec would finish in one invocation but
would change the shape of the command for humans too, which Y007 forbids.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import exploding_input, write_config

pytestmark = [pytest.mark.platform]


class _Ok:
    returncode = 0


@pytest.mark.platform
def test_e008_unit_006_first_run_names_its_successor(tmp_path, monkeypatch, capsys):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "3.106.0", "4.27.0"),
         ), \
         patch("atdd.coach.commands.upgrader.auto_upgrade", return_value=True), \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc = Upgrader(repo_root=tmp_path).run(yes=False)

    out = capsys.readouterr().out
    assert rc == 0, f"the first step must succeed, got {rc}"
    assert "atdd upgrade" in out, (
        f"the first run must name the exact command to run next; output was:\n{out}"
    )


@pytest.mark.platform
def test_e008_unit_006_first_run_does_not_replace_itself(tmp_path, monkeypatch):
    """No os.exec* and no relaunch of the upgraded binary — operator decision."""
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    exec_calls = []

    def forbidden(*args, **kwargs):
        exec_calls.append(args)
        raise AssertionError("upgrader must not re-exec itself")

    patches = []
    for name in ("execv", "execve", "execvp", "execvpe", "execl", "execlp"):
        if hasattr(os, name):
            patches.append(patch.object(os, name, side_effect=forbidden))

    with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "3.106.0", "4.27.0"),
         ), \
         patch("atdd.coach.commands.upgrader.auto_upgrade", return_value=True), \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        for p in patches:
            p.start()
        try:
            rc = Upgrader(repo_root=tmp_path).run(yes=False)
        finally:
            for p in patches:
                p.stop()

    assert exec_calls == [], f"upgrader re-executed itself: {exec_calls}"
    assert rc == 0


@pytest.mark.platform
def test_e008_unit_006_second_run_finishes_the_sync_and_a_third_is_a_no_op(tmp_path, monkeypatch):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    # Step two: the install is now current, the stamp is not.
    #
    # Both readers of "the installed version" must be patched. Upgrader prints
    # its own `installed`, but update_toolkit_version re-derives it from
    # atdd.version_check.__version__ and that is what actually lands in the
    # stamp. Patching only the first leaves the fixture incoherent: the run
    # reports 4.27.0 and writes whatever the machine really has. This surfaced
    # when the shared install moved 4.27.0 -> 4.28.0 mid-session.
    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch("atdd.version_check.__version__", "4.27.0"), \
         patch("atdd.coach.commands.upgrader.subprocess.run", return_value=_Ok()) as ran, \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc_two = Upgrader(repo_root=tmp_path).run(yes=False, no_pypi=True)

    assert rc_two == 0, f"the second step must succeed, got {rc_two}"
    assert ran.call_count >= 2, "the second step must run sync and init --force"

    # Step three: nothing left to do.
    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch("atdd.version_check.__version__", "4.27.0"), \
         patch("atdd.coach.commands.upgrader.subprocess.run") as ran_again, \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        rc_three = Upgrader(repo_root=tmp_path).run(yes=False, no_pypi=True)

    assert rc_three == 0, f"the third run must be a clean no-op, got {rc_three}"
    ran_again.assert_not_called()
