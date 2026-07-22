# URN: test:govern-lifecycle:coach-operator-safety-invariants:E064-UNIT-003-upgrade-banner-does-not-suggest-force
# Acceptance: acc:govern-lifecycle:E068-UNIT-003-upgrade-banner-does-not-suggest-force
# WMBT: wmbt:govern-lifecycle:E068
# Phase: GREEN
# Layer: backend.unit
# Assertion: structural
"""E022-UNIT-003 — check_upgrade_sync_needed() banner must not contain '--force'.

Same problem class as E022-UNIT-001 (advertising destructive paths to agents):
the ⚠️ upgrade banner emitted by `check_upgrade_sync_needed()` previously
read "Run: atdd sync && atdd init --force", which would teach agents to run
`atdd init --force` on every upgrade — a destructive init that overwrites
operator-customized files.

Phase GREEN: version_check.py is edited to drop '&& atdd init --force',
leaving only 'Run: atdd sync'. This test verifies both:
  1. The banner still contains 'atdd sync' (the correct upgrade step).
  2. The banner does NOT contain '--force'.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def _get_banner_string() -> str:
    """Return the upgrade banner string from check_upgrade_sync_needed().

    We patch the internals so the function believes an upgrade happened
    (last_version=3.0.0, current=3.1.0) without needing a real .atdd/config.yaml
    or filesystem state.
    """
    from atdd.version_check import check_upgrade_sync_needed  # noqa: PLC0415

    # Patch all gatekeepers so the function runs in a controlled environment:
    #   __version__              → non-"0.0.0" so the dev-install early-return is skipped
    #                              (CI uses PYTHONPATH=src without installing the package,
    #                              so importlib.metadata raises PackageNotFoundError → "0.0.0")
    #   _load_repo_config        → returns a fake config dict + path
    #   _get_last_toolkit_version → returns an older version so upgrade is detected
    #   _is_newer                → unconditionally True
    fake_config = {"toolkit": {"last_version": "3.0.0"}}
    with (
        patch("atdd.version_check.__version__", "3.1.0"),
        patch(
            "atdd.version_check._load_repo_config",
            return_value=(fake_config, None),
        ),
        patch(
            "atdd.version_check._get_last_toolkit_version",
            return_value="3.0.0",
        ),
        patch(
            "atdd.version_check._is_newer",
            return_value=True,
        ),
    ):
        banner = check_upgrade_sync_needed()

    return banner or ""


def test_upgrade_banner_does_not_contain_force():
    """E022-UNIT-003: upgrade banner must not advertise '--force' to agents."""
    banner = _get_banner_string()

    assert banner, (
        "check_upgrade_sync_needed() returned None/empty — expected a banner string.\n"
        "Check that the mock patches are compatible with the current implementation."
    )

    assert "--force" not in banner, (
        f"Upgrade banner contains '--force':\n  {banner!r}\n\n"
        "E022-UNIT-003 requires the banner to omit '--force' so agents reading\n"
        "it cannot discover the destructive 'atdd init --force' flag.\n"
        "Fix: edit check_upgrade_sync_needed() in src/atdd/version_check.py to\n"
        "use 'Run: atdd sync' instead of 'Run: atdd sync && atdd init --force'."
    )


def test_upgrade_banner_still_contains_atdd_sync():
    """E022-UNIT-003 (guard): banner still references 'atdd sync' after the --force removal."""
    banner = _get_banner_string()

    assert "atdd sync" in banner, (
        f"Upgrade banner does not contain 'atdd sync':\n  {banner!r}\n\n"
        "The --force removal must not also strip the 'atdd sync' instruction.\n"
        "Fix: ensure check_upgrade_sync_needed() returns a message containing\n"
        "'atdd sync' so operators know to run the sync command."
    )


def test_upgrade_notes_entry_1_16_4_does_not_contain_force():
    """E022-UNIT-003 (upgrade notes): the 1.16.4 upgrade note must not mention '--force'."""
    from atdd.version_check import UPGRADE_NOTES  # noqa: PLC0415

    note_1_16_4 = UPGRADE_NOTES.get("1.16.4", "")

    assert "--force" not in note_1_16_4, (
        f"UPGRADE_NOTES['1.16.4'] contains '--force': {note_1_16_4!r}\n\n"
        "E022 covers all banner and upgrade-note paths. Remove '--force' from\n"
        "the 1.16.4 upgrade note in src/atdd/version_check.py::UPGRADE_NOTES."
    )
