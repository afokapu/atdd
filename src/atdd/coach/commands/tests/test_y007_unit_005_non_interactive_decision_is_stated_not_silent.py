# URN: test:integration-hardening:run-upgrade-unattended:Y007-UNIT-005-non-interactive-decision-is-stated-not-silent
# Acceptance: acc:integration-hardening:Y007-UNIT-005-non-interactive-decision-is-stated-not-silent
# WMBT: wmbt:integration-hardening:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""Y007-UNIT-005 — a run that answered its own prompt says so.

RED Test for acc:integration-hardening:Y007-UNIT-005-non-interactive-decision-is-stated-not-silent
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:Y007
Purpose: Match the repo's loud-over-silent posture (managed hooks fail closed
with no bypass env var; manifest_migration refuses a whole run rather than
write a half-valid corpus). A silently self-answering prompt would be the
opposite of that.
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from atdd.coach.commands.upgrader import Upgrader

from ._upgrade_unattended_helpers import (
    exploding_input,
    find_upgrader_source,
    write_config,
)

pytestmark = [pytest.mark.platform]


@pytest.mark.platform
def test_y007_unit_005_no_tty_run_states_its_decision(tmp_path, monkeypatch, capsys):
    write_config(tmp_path, last_version="3.106.0")
    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.commands.upgrader.__version__", "3.106.0"), \
         patch(
             "atdd.coach.commands.upgrader.is_outdated",
             return_value=(True, "3.106.0", "4.27.0"),
         ), \
         patch("atdd.coach.commands.upgrader.auto_upgrade", return_value=(True, "")), \
         patch("sys.stdin.isatty", return_value=False), \
         patch("builtins.input", side_effect=exploding_input):
        Upgrader(repo_root=tmp_path).run(yes=False)

    out = capsys.readouterr().out.lower()

    # It must be visible in a log that no terminal was found...
    assert any(t in out for t in ("no terminal", "not a terminal", "non-interactive")), (
        "a self-answered confirmation must state that no terminal was detected; "
        f"output was:\n{out}"
    )
    # ...and what the run decided to do as a result.
    assert "upgrade" in out, f"the decided action must be named; output was:\n{out}"


@pytest.mark.platform
def test_y007_unit_005_no_bypass_environment_variable_exists():
    """The only override is the --yes flag that already exists on the CLI.

    An env var that switches the non-interactive default back off would be
    precisely the silent-degradation escape hatch the managed hooks refuse to
    ship.
    """
    source = find_upgrader_source()

    env_reads = re.findall(r"(?:os\.environ(?:\.get)?|getenv)\s*[\(\[]\s*['\"]([A-Z0-9_]+)", source)
    offenders = [
        name for name in env_reads
        if any(tok in name for tok in ("TTY", "INTERACT", "PROMPT", "YES", "ASSUME", "FORCE"))
    ]
    assert offenders == [], (
        "upgrader.py must define no bypass environment variable for the "
        f"non-interactive default; found: {offenders}"
    )
