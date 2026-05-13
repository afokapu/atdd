"""Walker test: every decommissioned-stub subcommand must show DEPRECATED in --help.

acc:discover-and-decommission:E003-UNIT-001-migration-message-reused
acc:discover-and-decommission:E003-INTEGRATION-003-canonical-alternatives-named
acc:discover-and-decommission:E003-INTEGRATION-004-walker-test-passes

Detection convention: any module under atdd.coach.commands.* that defines
MIGRATION_MESSAGE at module level is treated as a decommissioned stub.  The
corresponding CLI subcommand name equals the module's filename stem (e.g.
babysit.py → ``atdd babysit``).
"""
from __future__ import annotations

import contextlib
import importlib
import io
import sys
from pathlib import Path
from typing import List

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_stub_subcommands() -> List[str]:
    """Return sorted subcommand names whose command module defines MIGRATION_MESSAGE."""
    commands_dir = Path(__file__).parent.parent / "commands"
    stubs: List[str] = []
    for py_file in sorted(commands_dir.glob("*.py")):
        if py_file.stem.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"atdd.coach.commands.{py_file.stem}")
        except Exception:
            continue
        if hasattr(mod, "MIGRATION_MESSAGE"):
            stubs.append(py_file.stem)
    return stubs


def _get_subcommand_help(subcommand: str) -> str:
    """Return the combined stdout+stderr output of ``atdd <subcommand> --help``."""
    import atdd.cli as _cli_module  # noqa: PLC0415

    old_argv = sys.argv[:]
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    sys.argv = ["atdd", subcommand, "--help"]
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                _cli_module.main()
            except SystemExit:
                pass
    finally:
        sys.argv = old_argv
    return stdout_buf.getvalue() + stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# UNIT-001: MIGRATION_MESSAGE exists in babysit.py and is the source of truth
# ---------------------------------------------------------------------------

def test_migration_message_defined_in_babysit() -> None:
    """acc:discover-and-decommission:E003-UNIT-001-migration-message-reused

    babysit.py::MIGRATION_MESSAGE must exist and contain the three canonical
    alternatives so it serves as the single source of truth imported by cli.py.
    """
    from atdd.coach.commands.babysit import MIGRATION_MESSAGE  # noqa: PLC0415

    assert MIGRATION_MESSAGE, "MIGRATION_MESSAGE must be a non-empty string"
    for expected in ("atdd observer status", "atdd observer aggregate-approve", "atdd coach"):
        assert expected in MIGRATION_MESSAGE, (
            f"MIGRATION_MESSAGE is missing canonical alternative '{expected}'. "
            f"babysit.py is the source of truth — all three alternatives must live here."
        )


# ---------------------------------------------------------------------------
# INTEGRATION-003: babysit --help names all three canonical alternatives
# ---------------------------------------------------------------------------

def test_canonical_alternatives_named() -> None:
    """acc:discover-and-decommission:E003-INTEGRATION-003-canonical-alternatives-named

    ``atdd babysit --help`` output must name the three canonical replacements.
    """
    help_text = _get_subcommand_help("babysit")
    for expected in (
        "atdd observer status",
        "atdd observer aggregate-approve",
        "atdd coach",
    ):
        assert expected in help_text, (
            f"`atdd babysit --help` is missing canonical alternative '{expected}'. "
            f"All three must be listed per spec §0.2 absorption map."
        )


# ---------------------------------------------------------------------------
# INTEGRATION-004: walker enumerates every stub and asserts DEPRECATED in help
# ---------------------------------------------------------------------------

_STUBS = _collect_stub_subcommands()


def test_walker_finds_at_least_one_stub() -> None:
    """acc:discover-and-decommission:E003-INTEGRATION-004-walker-test-passes (guard)

    The walker must enumerate at least one stub so parametrize is never vacuously true.
    """
    assert _STUBS, (
        "No stubs found under atdd.coach.commands.*. "
        "Expected at least babysit.py to define MIGRATION_MESSAGE."
    )


@pytest.mark.parametrize("subcommand", _STUBS)
def test_decommissioned_subcommand_help(subcommand: str) -> None:
    """acc:discover-and-decommission:E003-INTEGRATION-004-walker-test-passes

    Every decommissioned-stub subcommand must show DEPRECATED in --help output.
    """
    help_text = _get_subcommand_help(subcommand)
    assert "DEPRECATED" in help_text, (
        f"`atdd {subcommand} --help` does not contain 'DEPRECATED'. "
        f"Decommissioned stubs must expose a deprecation marker at help-render time "
        f"so operators are not misled into planning workflows around removed commands."
    )
