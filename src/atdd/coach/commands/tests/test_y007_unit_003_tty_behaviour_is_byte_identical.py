# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-003-tty-behaviour-is-byte-identical
# Acceptance: acc:integration-hardening:Y007-UNIT-003-tty-behaviour-is-byte-identical
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-003 — a human at a terminal sees exactly what they see today.

RED Test for acc:integration-hardening:Y007-UNIT-003-tty-behaviour-is-byte-identical
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: Both prompts are still asked and a declining answer still skips or
aborts identically. Only the no-TTY path is new.

TESTER NOTE (#1628): the behavioural half of this acceptance CANNOT fail first
— today's implementation already prompts on a TTY, which is the whole point of
"unchanged". What can and does fail first is the resolver the Y007 statement
names: an explicit flag wins, else the answer comes from isatty. That is the
new contract, and it is asserted below alongside the unchanged prompts. Without
it this file would be a passing test in a RED phase, which flatters the plan
rather than testing it.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import require_symbol, write_config

pytestmark = [pytest.mark.platform]


class _Ok:
    returncode = 0


@pytest.mark.platform
def test_y007_unit_003_tty_pypi_prompt_unchanged(tmp_path, monkeypatch, capsys):
    """Declining on the PyPI branch still skips, exactly as before."""
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    prompts = []

    def answer_no(prompt=""):
        prompts.append(prompt)
        return "n"

    with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "3.106.0", "4.27.0"),
         ), \
         patch("atdd.coach.commands.upgrader.auto_upgrade") as mock_upgrade, \
         patch("sys.stdin.isatty", return_value=True), \
         patch("builtins.input", side_effect=answer_no):
        Upgrader(repo_root=tmp_path).run(yes=False)

    assert len(prompts) == 1, f"a TTY must still be prompted once, got {prompts!r}"
    assert "now? [Y/n]" in prompts[0], f"prompt text changed: {prompts[0]!r}"
    mock_upgrade.assert_not_called()
    assert "Skipping upgrade" in capsys.readouterr().out


@pytest.mark.platform
def test_y007_unit_003_tty_sync_prompt_unchanged(tmp_path, monkeypatch):
    """Declining on the local-sync branch still aborts with rc=1."""
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    prompts = []

    def answer_no(prompt=""):
        prompts.append(prompt)
        return "n"

    with patch("atdd.coach.commands.upgrader.__version__", "4.27.0"), \
         patch("atdd.coach.commands.upgrader.subprocess.run", return_value=_Ok()) as ran, \
         patch("sys.stdin.isatty", return_value=True), \
         patch("builtins.input", side_effect=answer_no):
        rc = Upgrader(repo_root=tmp_path).run(yes=False, no_pypi=True)

    assert rc == 1, f"declining must abort with rc=1, got {rc}"
    assert prompts == ["Proceed? [Y/n] "], f"prompt text changed: {prompts!r}"
    ran.assert_not_called()


@pytest.mark.platform
def test_y007_unit_003_resolver_prefers_explicit_flag_over_isatty():
    """The new contract: explicit flag wins, else infer from isatty.

    Mirrors coach.resolve_no_prompt (coach.py:255). This is the half that fails
    first — the symbol does not exist yet.
    """
    resolve = require_symbol("resolve_confirmation")

    # No explicit flag: the terminal decides.
    assert resolve(None, True) is False, "a TTY with no flag must still prompt"
    assert resolve(None, False) is True, "no TTY with no flag must resolve itself"

    # Explicit flag wins in both directions, regardless of the terminal.
    assert resolve(True, True) is True, "--yes must win on a TTY"
    assert resolve(True, False) is True, "--yes must win with no TTY"
